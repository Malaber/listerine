import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jose import jwt
from starlette.requests import Request

from app.api.v1.routes.auth import _origin_for_request, _password_auth_disabled, _rp_id_for_request
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.services.websocket_hub import WebSocketHub
from app.web.routes import _get_session_user, _has_session_access_token


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


def test_has_session_access_token_rejects_invalid_jwt() -> None:
    request = Request({"type": "http", "headers": [], "session": {"access_token": "bad-token"}})

    assert _has_session_access_token(request) is False


def test_has_session_access_token_rejects_missing_token_and_subject() -> None:
    request_without_token = Request({"type": "http", "headers": [], "session": {}})
    assert _has_session_access_token(request_without_token) is False

    token_without_subject = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    request_without_subject = Request(
        {
            "type": "http",
            "headers": [],
            "session": {"access_token": token_without_subject},
        }
    )
    assert _has_session_access_token(request_without_subject) is False


def test_get_session_user_clears_invalid_session_payloads() -> None:
    token_without_subject = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    request = Request(
        {
            "type": "http",
            "headers": [],
            "session": {"access_token": token_without_subject},
        }
    )

    assert asyncio.run(_get_session_user(request, None)) is None
    assert request.session == {}


def test_passkey_request_helpers() -> None:
    request = Request(
        {
            "type": "http",
            "scheme": "http",
            "path": "/login",
            "server": ("localhost", 8000),
            "headers": [(b"host", b"localhost:8000")],
        }
    )

    assert _rp_id_for_request(request) == "localhost"
    assert _origin_for_request(request) == "http://localhost:8000"
    assert _password_auth_disabled().status_code == 400

    hostless_request = Request({"type": "http", "scheme": "http", "path": "/", "headers": []})
    assert _password_auth_disabled().detail.startswith("Password-based auth is disabled")
    try:
        _rp_id_for_request(hostless_request)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:  # pragma: no cover
        raise AssertionError("Expected hostless passkey request to fail")
