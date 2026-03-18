from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_admin_user, get_current_user
from app.core.database import get_db
from app.models import Category, GroceryItem, ListCategoryOrder, User
from app.schemas.domain import CategoryCreate, CategoryOut

router = APIRouter(tags=["categories"])


@router.post("/categories", response_model=CategoryOut)
async def create_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    ensure_admin_user(user)
    category = Category(
        household_id=None,
        name=payload.name,
        color=payload.color,
    )
    category.aliases = payload.aliases
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Category]:
    result = await db.execute(select(Category).order_by(Category.name.asc()))
    return list(result.scalars().all())


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: UUID,
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Category:
    ensure_admin_user(user)
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one()
    category.name = payload.name
    category.color = payload.color
    category.aliases = payload.aliases
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    ensure_admin_user(user)
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one()
    item_result = await db.execute(
        select(GroceryItem).where(GroceryItem.category_id == category_id)
    )
    for item in item_result.scalars().all():
        item.category_id = None

    order_result = await db.execute(
        select(ListCategoryOrder).where(ListCategoryOrder.category_id == category_id)
    )
    for order in order_result.scalars().all():
        await db.delete(order)

    await db.delete(category)
    await db.commit()
    return {"message": "deleted"}
