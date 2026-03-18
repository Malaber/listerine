from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[UUID, list[WebSocket]] = defaultdict(list)

    async def connect(self, list_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[list_id].append(websocket)

    def disconnect(self, list_id: UUID, websocket: WebSocket) -> None:
        conns = self._connections.get(list_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns and list_id in self._connections:
            del self._connections[list_id]

    async def broadcast(self, list_id: UUID, event: dict) -> None:
        for conn in list(self._connections.get(list_id, [])):
            await conn.send_json(event)


hub = WebSocketHub()
