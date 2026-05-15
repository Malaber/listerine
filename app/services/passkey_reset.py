import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PasskeyAddLink, User

PASSKEY_RESET_TTL = timedelta(hours=24)


def hash_passkey_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_passkey_reset_token() -> str:
    return secrets.token_urlsafe(32)


def passkey_reset_expires_at(ttl: timedelta | None = None) -> datetime:
    return datetime.now(UTC) + (ttl or PASSKEY_RESET_TTL)


def passkey_reset_is_active(link: PasskeyAddLink, *, now: datetime | None = None) -> bool:
    if link.used_at is not None:
        return False
    if not link.token_hash or link.expires_at is None:
        return False
    current_time = now or datetime.now(UTC)
    expires_at = link.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    else:
        expires_at = expires_at.astimezone(UTC)
    return expires_at > current_time


def set_passkey_reset(user: User, token: str, *, ttl: timedelta | None = None) -> PasskeyAddLink:
    expires_at = passkey_reset_expires_at(ttl)
    return PasskeyAddLink(
        user_id=user.id,
        token_hash=hash_passkey_reset_token(token),
        expires_at=expires_at,
    )


async def issue_passkey_reset(
    db: AsyncSession, user: User, *, ttl: timedelta | None = None
) -> tuple[str, PasskeyAddLink]:
    token = create_passkey_reset_token()
    link = set_passkey_reset(user, token, ttl=ttl)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return token, link


def build_passkey_add_link(base_url: str, token: str, *, identifier: str | None = None) -> str:
    normalized_base_url = base_url.strip().rstrip("/")
    if not normalized_base_url:
        raise ValueError("Base URL is required")
    link = f"{normalized_base_url}/passkey-add/{token}"
    if identifier is not None:
        return f"{link}#identifier={identifier}"
    return link


def clear_passkey_reset(link: PasskeyAddLink) -> None:
    link.used_at = datetime.now(UTC)


async def get_passkey_add_link_for_token(
    db: AsyncSession,
    token: str,
    *,
    with_passkeys: bool = False,
) -> PasskeyAddLink | None:
    query = select(PasskeyAddLink).where(
        PasskeyAddLink.token_hash == hash_passkey_reset_token(token)
    )
    if with_passkeys:
        query = query.options(selectinload(PasskeyAddLink.user).selectinload(User.passkeys))
    else:
        query = query.options(selectinload(PasskeyAddLink.user))
    result = await db.execute(query)
    link = result.scalar_one_or_none()
    if link is None or not passkey_reset_is_active(link):
        return None
    return link


async def get_user_for_passkey_reset_token(
    db: AsyncSession,
    token: str,
    *,
    with_passkeys: bool = False,
) -> User | None:
    link = await get_passkey_add_link_for_token(
        db,
        token,
        with_passkeys=with_passkeys,
    )
    if link is None:
        return None
    return link.user
