from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_household_member, get_current_user, get_list_for_user
from app.core.database import get_db
from app.models import Category, GroceryList, ListCategoryOrder, User
from app.schemas.domain import (
    GroceryListCreate,
    GroceryListOut,
    ListCategoryOrderOut,
    ListCategoryOrderUpdate,
)
from app.services.websocket_hub import hub

router = APIRouter(tags=["lists"])


async def _broadcast_category_order(
    list_id: UUID, user_id: UUID, orders: list[ListCategoryOrder]
) -> None:
    payload = [
        ListCategoryOrderOut(category_id=order.category_id, sort_order=order.sort_order).model_dump(
            mode="json"
        )
        for order in orders
    ]
    await hub.broadcast(
        list_id,
        {
            "type": "category_order_updated",
            "list_id": str(list_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_user_id": str(user_id),
            "payload": {"category_order": payload},
        },
    )


@router.post("/households/{household_id}/lists", response_model=GroceryListOut)
async def create_list(
    household_id: UUID,
    payload: GroceryListCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryList:
    await ensure_household_member(db, household_id, user.id)
    grocery_list = GroceryList(household_id=household_id, name=payload.name, created_by=user.id)
    db.add(grocery_list)
    await db.commit()
    await db.refresh(grocery_list)
    return grocery_list


@router.get("/households/{household_id}/lists", response_model=list[GroceryListOut])
async def list_lists(
    household_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GroceryList]:
    await ensure_household_member(db, household_id, user.id)
    result = await db.execute(select(GroceryList).where(GroceryList.household_id == household_id))
    return list(result.scalars().all())


@router.get("/lists/{list_id}", response_model=GroceryListOut)
async def get_list(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GroceryList:
    return await get_list_for_user(db, list_id, user.id)


@router.get("/lists/{list_id}/category-order", response_model=list[ListCategoryOrderOut])
async def get_list_category_order(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[ListCategoryOrder]:
    await get_list_for_user(db, list_id, user.id)
    result = await db.execute(
        select(ListCategoryOrder)
        .where(ListCategoryOrder.list_id == list_id)
        .order_by(ListCategoryOrder.sort_order.asc(), ListCategoryOrder.category_id.asc())
    )
    return list(result.scalars().all())


@router.put("/lists/{list_id}/category-order", response_model=list[ListCategoryOrderOut])
async def update_list_category_order(
    list_id: UUID,
    payload: ListCategoryOrderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ListCategoryOrder]:
    await get_list_for_user(db, list_id, user.id)

    category_ids = payload.category_ids
    if len(category_ids) != len(set(category_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category order contains duplicate categories.",
        )

    if category_ids:
        category_result = await db.execute(select(Category.id).where(Category.id.in_(category_ids)))
        existing_ids = set(category_result.scalars().all())
        if existing_ids != set(category_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category order references an unknown category.",
            )

    await db.execute(delete(ListCategoryOrder).where(ListCategoryOrder.list_id == list_id))
    orders: list[ListCategoryOrder] = []
    for index, category_id in enumerate(category_ids):
        order = ListCategoryOrder(list_id=list_id, category_id=category_id, sort_order=index)
        db.add(order)
        orders.append(order)

    await db.commit()
    for order in orders:
        await db.refresh(order)
    await _broadcast_category_order(list_id, user.id, orders)
    return orders


@router.delete("/lists/{list_id}")
async def delete_list(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    grocery_list = await get_list_for_user(db, list_id, user.id)
    await db.execute(delete(ListCategoryOrder).where(ListCategoryOrder.list_id == list_id))
    await db.delete(grocery_list)
    await db.commit()
    return {"message": "deleted"}


@router.patch("/lists/{list_id}", response_model=GroceryListOut)
async def patch_list(
    list_id: UUID,
    payload: GroceryListCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryList:
    grocery_list = await get_list_for_user(db, list_id, user.id)
    if not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    grocery_list.name = payload.name
    await db.commit()
    await db.refresh(grocery_list)
    return grocery_list
