from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.deps import get_current_user, get_list_for_user
from app.core.database import get_db
from app.models import GroceryItem, ListCategoryOrder
from app.schemas.domain import GroceryItemOut, ListCategoryOrderOut
from app.services.websocket_hub import hub

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/lists/{list_id}")
async def ws_list(websocket: WebSocket, list_id: UUID) -> None:
    db_gen = get_db()
    db = await anext(db_gen)
    try:
        user = await get_current_user(websocket, db, websocket.query_params.get("token"))
        await get_list_for_user(db, list_id, user.id)
        await hub.connect(list_id, websocket)
        result = await db.execute(select(GroceryItem).where(GroceryItem.list_id == list_id))
        snapshot = [
            GroceryItemOut.model_validate(row).model_dump(mode="json") for row in result.scalars()
        ]
        category_order_result = await db.execute(
            select(ListCategoryOrder)
            .where(ListCategoryOrder.list_id == list_id)
            .order_by(ListCategoryOrder.sort_order.asc(), ListCategoryOrder.category_id.asc())
        )
        category_order = [
            ListCategoryOrderOut(category_id=row.category_id, sort_order=row.sort_order).model_dump(
                mode="json"
            )
            for row in category_order_result.scalars()
        ]
        await websocket.send_json(
            {
                "type": "list_snapshot",
                "list_id": str(list_id),
                "timestamp": datetime.now(UTC).isoformat(),
                "actor_user_id": str(user.id),
                "payload": {"items": snapshot, "category_order": category_order},
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(list_id, websocket)
    finally:
        await db_gen.aclose()
