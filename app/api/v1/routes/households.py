from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_household_member, get_current_user
from app.core.database import get_db
from app.models import Household, HouseholdMember, User
from app.schemas.domain import HouseholdCreate, HouseholdOut

router = APIRouter(prefix="/households", tags=["households"])


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
