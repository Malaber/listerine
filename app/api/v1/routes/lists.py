from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_household_member, get_current_user, get_list_for_user
from app.core.database import get_db
from app.models import (
    Category,
    GroceryItem,
    GroceryList,
    ListCategoryOrder,
    ListDisabledCategory,
    User,
)
from app.schemas.domain import (
    CategoryOut,
    GroceryListCreate,
    GroceryListOut,
    ListCategoryOrderOut,
    ListCategoryOrderUpdate,
    ListDisabledCategoriesOut,
    ListDisabledCategoriesUpdate,
    GroceryItemOut,
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


async def _broadcast_disabled_categories(
    list_id: UUID, user_id: UUID, category_ids: list[UUID]
) -> None:
    await hub.broadcast(
        list_id,
        {
            "type": "category_disabled_categories_updated",
            "list_id": str(list_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_user_id": str(user_id),
            "payload": {"category_ids": [str(category_id) for category_id in category_ids]},
        },
    )


async def _broadcast_item_updated(list_id: UUID, user_id: UUID, item: GroceryItem) -> None:
    await hub.broadcast(
        list_id,
        {
            "type": "item_updated",
            "list_id": str(list_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_user_id": str(user_id),
            "payload": {"item": GroceryItemOut.model_validate(item).model_dump(mode="json")},
        },
    )


async def _accessible_categories_by_id(
    db: AsyncSession, grocery_list: GroceryList, category_ids: set[UUID]
) -> dict[UUID, Category]:
    if not category_ids:
        return {}

    result = await db.execute(
        select(Category).where(
            Category.id.in_(category_ids),
            (Category.household_id.is_(None))
            | (Category.household_id == grocery_list.household_id),
        )
    )
    return {category.id: category for category in result.scalars().all()}


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


@router.get("/lists/{list_id}/categories", response_model=list[CategoryOut])
async def get_list_categories(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Category]:
    grocery_list = await get_list_for_user(db, list_id, user.id)
    result = await db.execute(
        select(Category)
        .where(
            (Category.household_id.is_(None)) | (Category.household_id == grocery_list.household_id)
        )
        .order_by(Category.name.asc())
    )
    return list(result.scalars().all())


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
    grocery_list = await get_list_for_user(db, list_id, user.id)

    category_ids = payload.category_ids
    if len(category_ids) != len(set(category_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category order contains duplicate categories.",
        )

    if category_ids:
        categories_by_id = await _accessible_categories_by_id(db, grocery_list, set(category_ids))
        if set(categories_by_id) != set(category_ids):
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


@router.get("/lists/{list_id}/disabled-categories", response_model=ListDisabledCategoriesOut)
async def get_list_disabled_categories(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ListDisabledCategoriesOut:
    await get_list_for_user(db, list_id, user.id)
    result = await db.execute(
        select(ListDisabledCategory)
        .where(ListDisabledCategory.list_id == list_id)
        .order_by(ListDisabledCategory.category_id.asc())
    )
    return ListDisabledCategoriesOut(
        category_ids=[entry.category_id for entry in result.scalars().all()]
    )


@router.put("/lists/{list_id}/disabled-categories", response_model=ListDisabledCategoriesOut)
async def update_list_disabled_categories(
    list_id: UUID,
    payload: ListDisabledCategoriesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListDisabledCategoriesOut:
    grocery_list = await get_list_for_user(db, list_id, user.id)

    category_ids = payload.category_ids
    category_id_set = set(category_ids)
    if len(category_ids) != len(category_id_set):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disabled categories contain duplicate categories.",
        )

    categories_by_id = await _accessible_categories_by_id(db, grocery_list, category_id_set)
    if set(categories_by_id) != category_id_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Disabled categories reference an unknown category.",
        )

    await db.execute(delete(ListDisabledCategory).where(ListDisabledCategory.list_id == list_id))
    ordered_category_ids = [
        category.id
        for category in sorted(categories_by_id.values(), key=lambda category: category.name)
    ]
    for category_id in ordered_category_ids:
        db.add(ListDisabledCategory(list_id=list_id, category_id=category_id))

    affected_items: list[GroceryItem] = []
    if category_id_set:
        item_result = await db.execute(
            select(GroceryItem).where(
                GroceryItem.list_id == list_id,
                GroceryItem.category_id.in_(category_id_set),
            )
        )
        affected_items = list(item_result.scalars().all())
        for item in affected_items:
            item.category_id = None
            item.updated_by = user.id

    await db.commit()
    for item in affected_items:
        await db.refresh(item)

    await _broadcast_disabled_categories(list_id, user.id, ordered_category_ids)
    for item in affected_items:
        await _broadcast_item_updated(list_id, user.id, item)
    return ListDisabledCategoriesOut(category_ids=ordered_category_ids)


@router.delete("/lists/{list_id}")
async def delete_list(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    grocery_list = await get_list_for_user(db, list_id, user.id)
    await db.execute(delete(ListDisabledCategory).where(ListDisabledCategory.list_id == list_id))
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
