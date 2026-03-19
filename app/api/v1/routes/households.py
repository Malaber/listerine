import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_household_member, get_current_user
from app.core.database import get_db
from app.models import Household, HouseholdInvite, HouseholdMember, User
from app.schemas.domain import (
    HouseholdCreate,
    HouseholdInviteOut,
    HouseholdInvitePreviewOut,
    HouseholdOut,
)

router = APIRouter(prefix="/households", tags=["households"])


def _hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _get_valid_invite(db: AsyncSession, token: str) -> HouseholdInvite:
    result = await db.execute(
        select(HouseholdInvite).where(HouseholdInvite.token_hash == _hash_invite_token(token))
    )
    invite = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if invite is None or _as_utc(invite.expires_at) <= now or invite.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite link is invalid.")
    return invite


@router.post("", response_model=HouseholdOut)
async def create_household(
    payload: HouseholdCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Household:
    household = Household(name=payload.name, owner_user_id=user.id)
    db.add(household)
    await db.flush()
    db.add(HouseholdMember(household_id=household.id, user_id=user.id, role="owner"))
    await db.commit()
    await db.refresh(household)
    return household


@router.get("", response_model=list[HouseholdOut])
async def list_households(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Household]:
    result = await db.execute(
        select(Household).join(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    return list(result.scalars().all())


@router.get("/{household_id}", response_model=HouseholdOut)
async def get_household(
    household_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Household:
    await ensure_household_member(db, household_id, user.id)
    result = await db.execute(select(Household).where(Household.id == household_id))
    return result.scalar_one()


@router.post("/{household_id}/invites", response_model=HouseholdInviteOut)
async def create_household_invite(
    household_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HouseholdInviteOut:
    result = await db.execute(select(Household).where(Household.id == household_id))
    household = result.scalar_one_or_none()
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await ensure_household_member(db, household_id, user.id)
    if household.owner_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the household owner can create invite links.",
        )

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    invite = HouseholdInvite(
        household_id=household_id,
        created_by_user_id=user.id,
        token_hash=_hash_invite_token(token),
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()

    invite_url = str(request.base_url).rstrip("/") + f"/invite/{token}"
    return HouseholdInviteOut(invite_url=invite_url, expires_at=expires_at)


@router.get("/invites/{token}", response_model=HouseholdInvitePreviewOut)
async def get_household_invite(
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HouseholdInvitePreviewOut:
    invite = await _get_valid_invite(db, token)
    household_result = await db.execute(
        select(Household).where(Household.id == invite.household_id)
    )
    household = household_result.scalar_one()
    membership_result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.household_id == invite.household_id,
            HouseholdMember.user_id == user.id,
        )
    )
    return HouseholdInvitePreviewOut(
        household_id=household.id,
        household_name=household.name,
        expires_at=_as_utc(invite.expires_at),
        already_member=membership_result.scalar_one_or_none() is not None,
    )


@router.post("/invites/{token}/accept", response_model=HouseholdOut)
async def accept_household_invite(
    token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Household:
    invite = await _get_valid_invite(db, token)
    household_result = await db.execute(
        select(Household).where(Household.id == invite.household_id)
    )
    household = household_result.scalar_one()
    membership_result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.household_id == invite.household_id,
            HouseholdMember.user_id == user.id,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        db.add(HouseholdMember(household_id=invite.household_id, user_id=user.id, role="member"))

    invite.accepted_at = datetime.now(UTC)
    invite.accepted_by_user_id = user.id
    await db.commit()
    await db.refresh(household)
    return household
