from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_list_for_user
from app.core.database import get_db
from app.models import GroceryItem, User
from app.schemas.domain import GroceryItemCreate, GroceryItemOut, GroceryItemUpdate
from app.services.websocket_hub import hub

router = APIRouter(tags=["items"])


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


@router.post("/lists/{list_id}/items", response_model=GroceryItemOut)
async def create_item(
    list_id: UUID,
    payload: GroceryItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroceryItem:
    await get_list_for_user(db, list_id, user.id)
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
