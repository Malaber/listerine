import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import User

PASSKEY_RESET_TTL = timedelta(hours=24)


def hash_passkey_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_passkey_reset_token() -> str:
    return secrets.token_urlsafe(32)


def passkey_reset_expires_at() -> datetime:
    return datetime.now(UTC) + PASSKEY_RESET_TTL


def passkey_reset_is_active(user: User, *, now: datetime | None = None) -> bool:
    if not user.passkey_reset_token_hash or user.passkey_reset_expires_at is None:
        return False
    current_time = now or datetime.now(UTC)
    expires_at = user.passkey_reset_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    else:
        expires_at = expires_at.astimezone(UTC)
    return expires_at > current_time


def set_passkey_reset(user: User, token: str) -> datetime:
    expires_at = passkey_reset_expires_at()
    user.passkey_reset_token_hash = hash_passkey_reset_token(token)
    user.passkey_reset_expires_at = expires_at
    return expires_at


def clear_passkey_reset(user: User) -> None:
    user.passkey_reset_token_hash = None
    user.passkey_reset_expires_at = None


async def get_user_for_passkey_reset_token(
    db: AsyncSession,
    token: str,
    *,
    with_passkeys: bool = False,
) -> User | None:
    query = select(User).where(User.passkey_reset_token_hash == hash_passkey_reset_token(token))
    if with_passkeys:
        query = query.options(selectinload(User.passkeys))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user is None or not passkey_reset_is_active(user):
        return None
    return user
