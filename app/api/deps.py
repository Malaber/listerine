from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import GroceryList, HouseholdMember, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login/verify", auto_error=False)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
) -> User:
    session = getattr(request, "session", {})
    raw_token = token or session.get("access_token")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        payload = jwt.decode(raw_token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


async def ensure_household_member(db: AsyncSession, household_id: UUID, user_id: UUID) -> None:
    result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


async def get_list_for_user(db: AsyncSession, list_id: UUID, user_id: UUID) -> GroceryList:
    result = await db.execute(select(GroceryList).where(GroceryList.id == list_id))
    grocery_list = result.scalar_one_or_none()
    if grocery_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await ensure_household_member(db, grocery_list.household_id, user_id)
    return grocery_list
