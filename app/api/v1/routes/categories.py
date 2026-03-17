from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_household_member, get_current_user
from app.core.database import get_db
from app.models import Category, User
from app.schemas.domain import CategoryCreate, CategoryOut

router = APIRouter(tags=["categories"])


@router.post("/households/{household_id}/categories", response_model=CategoryOut)
async def create_category(
    household_id: UUID,
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    await ensure_household_member(db, household_id, user.id)
    category = Category(household_id=household_id, name=payload.name, color=payload.color)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/households/{household_id}/categories", response_model=list[CategoryOut])
async def list_categories(
    household_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Category]:
    await ensure_household_member(db, household_id, user.id)
    result = await db.execute(select(Category).where(Category.household_id == household_id))
    return list(result.scalars().all())


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: UUID,
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one()
    await ensure_household_member(db, category.household_id, user.id)
    category.name = payload.name
    category.color = payload.color
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one()
    await ensure_household_member(db, category.household_id, user.id)
    await db.delete(category)
    await db.commit()
    return {"message": "deleted"}
