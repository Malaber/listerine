import asyncio
from uuid import uuid4

from app.core.security import create_access_token, hash_password, verify_password
from app.services.websocket_hub import WebSocketHub


class DummyWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.events: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, event: dict) -> None:
        self.events.append(event)


def test_security_helpers_round_trip() -> None:
    password = "hello"
    password_hash = hash_password(password)
    assert verify_password(password, password_hash)
    assert not verify_password("bad", password_hash)
    assert isinstance(create_access_token(uuid4()), str)


def test_websocket_hub_connect_broadcast_disconnect() -> None:
    hub = WebSocketHub()
    list_id = uuid4()
    ws = DummyWebSocket()

    asyncio.run(hub.connect(list_id, ws))
    assert ws.accepted is True

    asyncio.run(hub.broadcast(list_id, {"type": "x"}))
    assert ws.events == [{"type": "x"}]

    hub.disconnect(list_id, ws)
    # cover no-op branch
    hub.disconnect(list_id, ws)


def test_security_helpers_handle_long_passwords() -> None:
    long_password = "x" * 100
    password_hash = hash_password(long_password)
    assert verify_password(long_password, password_hash)
