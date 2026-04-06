from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_list_for_user
from app.core.database import get_db
from app.models import Category, GroceryItem, User
from app.schemas.domain import (
    GroceryItemCreate,
    GroceryItemOut,
    GroceryItemsWindowOut,
    GroceryItemUpdate,
)
from app.services.websocket_hub import hub

router = APIRouter(tags=["items"])

CHECKED_ITEMS_INITIAL_LIMIT = 10
CHECKED_ITEMS_PAGE_SIZE = 100


async def _broadcast(event_type: str, user_id: UUID, item: GroceryItem) -> None:
    await hub.broadcast(
        item.list_id,
        {
            "type": event_type,
            "list_id": str(item.list_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_user_id": str(user_id),
            "payload": {"item": GroceryItemOut.model_validate(item).model_dump(mode="json")},
        },
    )


async def _validate_category_id(db: AsyncSession, category_id: UUID | None) -> None:
    if category_id is None:
        return

    result = await db.execute(select(Category.id).where(Category.id == category_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected category does not exist.",
        )


async def _checked_item_count(db: AsyncSession, list_id: UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(GroceryItem)
        .where(
            GroceryItem.list_id == list_id,
            GroceryItem.checked.is_(True),
        )
    )
    return int(result.scalar_one())


async def _checked_items_page(
    db: AsyncSession, list_id: UUID, *, offset: int, limit: int
) -> list[GroceryItem]:
    result = await db.execute(
        select(GroceryItem)
        .where(GroceryItem.list_id == list_id, GroceryItem.checked.is_(True))
        .order_by(GroceryItem.checked_at.desc(), GroceryItem.name.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/lists/{list_id}/items", response_model=GroceryItemOut)
async def create_item(
    list_id: UUID,
    payload: GroceryItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryItem:
    await get_list_for_user(db, list_id, user.id)
    await _validate_category_id(db, payload.category_id)
    item = GroceryItem(
        list_id=list_id,
        name=payload.name,
        quantity_text=payload.quantity_text,
        note=payload.note,
        category_id=payload.category_id,
        sort_order=payload.sort_order,
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await _broadcast("item_created", user.id, item)
    return item


@router.get("/lists/{list_id}/items", response_model=list[GroceryItemOut])
async def list_items(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[GroceryItem]:
    await get_list_for_user(db, list_id, user.id)
    result = await db.execute(select(GroceryItem).where(GroceryItem.list_id == list_id))
    return list(result.scalars().all())


@router.get("/lists/{list_id}/items/window", response_model=GroceryItemsWindowOut)
async def list_item_window(
    list_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GroceryItemsWindowOut:
    await get_list_for_user(db, list_id, user.id)
    active_result = await db.execute(
        select(GroceryItem).where(GroceryItem.list_id == list_id, GroceryItem.checked.is_(False))
    )
    checked_items = await _checked_items_page(
        db, list_id, offset=0, limit=CHECKED_ITEMS_INITIAL_LIMIT
    )
    checked_count = await _checked_item_count(db, list_id)
    items = list(active_result.scalars().all()) + checked_items
    return GroceryItemsWindowOut(
        items=[GroceryItemOut.model_validate(item) for item in items],
        checked_remaining_count=max(checked_count - len(checked_items), 0),
    )


@router.get("/lists/{list_id}/items/checked", response_model=list[GroceryItemOut])
async def list_checked_items(
    list_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(CHECKED_ITEMS_PAGE_SIZE, ge=1, le=CHECKED_ITEMS_PAGE_SIZE),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[GroceryItem]:
    await get_list_for_user(db, list_id, user.id)
    return await _checked_items_page(db, list_id, offset=offset, limit=limit)


@router.patch("/items/{item_id}", response_model=GroceryItemOut)
async def update_item(
    item_id: UUID,
    payload: GroceryItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryItem:
    result = await db.execute(select(GroceryItem).where(GroceryItem.id == item_id))
    item = result.scalar_one()
    await get_list_for_user(db, item.list_id, user.id)
    await _validate_category_id(
        db, payload.category_id if "category_id" in payload.model_fields_set else None
    )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_by = user.id
    await db.commit()
    await db.refresh(item)
    await _broadcast("item_updated", user.id, item)
    return item


@router.post("/items/{item_id}/check", response_model=GroceryItemOut)
async def check_item(
    item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GroceryItem:
    result = await db.execute(select(GroceryItem).where(GroceryItem.id == item_id))
    item = result.scalar_one()
    await get_list_for_user(db, item.list_id, user.id)
    item.checked = True
    item.checked_at = datetime.now(UTC)
    item.checked_by = user.id
    item.updated_by = user.id
    await db.commit()
    await db.refresh(item)
    await _broadcast("item_checked", user.id, item)
    return item


@router.post("/items/{item_id}/uncheck", response_model=GroceryItemOut)
async def uncheck_item(
    item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> GroceryItem:
    result = await db.execute(select(GroceryItem).where(GroceryItem.id == item_id))
    item = result.scalar_one()
    await get_list_for_user(db, item.list_id, user.id)
    item.checked = False
    item.checked_at = None
    item.checked_by = None
    item.updated_by = user.id
    await db.commit()
    await db.refresh(item)
    await _broadcast("item_unchecked", user.id, item)
    return item


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    result = await db.execute(select(GroceryItem).where(GroceryItem.id == item_id))
    item = result.scalar_one()
    await get_list_for_user(db, item.list_id, user.id)
    await db.delete(item)
    await db.commit()
    await hub.broadcast(
        item.list_id,
        {
            "type": "item_deleted",
            "list_id": str(item.list_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor_user_id": str(user.id),
            "payload": {"item": {"id": str(item.id)}},
        },
    )
    return {"message": "deleted"}
