import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from jose import jwt
from starlette.requests import Request

from app.admin import SessionAdminAuth, get_application_version
from app.api.v1.routes.auth import (
    _apply_bootstrap_admin_email,
    _origin_for_request,
    _password_auth_disabled,
    _rp_id_for_request,
)
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


class DummySessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class DummyDB:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.refresh_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, user) -> None:
        self.refresh_calls += 1


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


def test_get_application_version_reads_version_file(tmp_path, monkeypatch) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text("9.9.9\n", encoding="utf-8")
    monkeypatch.setattr("app.admin.VERSION_FILE", version_file)
    get_application_version.cache_clear()

    assert get_application_version() == "9.9.9"

    missing_version_file = tmp_path / "MISSING_VERSION"
    monkeypatch.setattr("app.admin.VERSION_FILE", missing_version_file)
    get_application_version.cache_clear()

    assert get_application_version() == "unknown"


def test_admin_auth_backend_redirects_and_allows(monkeypatch) -> None:
    auth = SessionAdminAuth()

    login_request = Request({"type": "http", "headers": [], "session": {}})
    login_response = asyncio.run(auth.login(login_request))
    assert login_response.headers["location"] == "/login"

    logout_request = Request({"type": "http", "headers": [], "session": {"access_token": "x"}})
    logout_response = asyncio.run(auth.logout(logout_request))
    assert logout_request.session == {}
    assert logout_response.headers["location"] == "/login"

    monkeypatch.setattr("app.admin.AsyncSessionLocal", lambda: DummySessionContext())

    anon_request = Request({"type": "http", "headers": [], "session": {}})

    async def _anon_user(request, session) -> None:
        return None

    monkeypatch.setattr("app.admin._get_session_user", _anon_user)
    anon_response = asyncio.run(auth.authenticate(anon_request))
    assert anon_response.headers["location"] == "/login"

    non_admin_request = Request({"type": "http", "headers": [], "session": {}})

    async def _non_admin_user(request, session) -> SimpleNamespace:
        return SimpleNamespace(is_admin=False)

    monkeypatch.setattr("app.admin._get_session_user", _non_admin_user)
    non_admin_response = asyncio.run(auth.authenticate(non_admin_request))
    assert non_admin_response.headers["location"] == "/"

    admin_request = Request({"type": "http", "headers": [], "session": {}})

    async def _admin_user(request, session) -> SimpleNamespace:
        return SimpleNamespace(is_admin=True)

    monkeypatch.setattr("app.admin._get_session_user", _admin_user)
    assert asyncio.run(auth.authenticate(admin_request)) is True


def test_bootstrap_admin_email_helper_respects_config(monkeypatch) -> None:
    db = DummyDB()
    user = SimpleNamespace(email="admin@example.com", is_admin=False)

    monkeypatch.setattr("app.api.v1.routes.auth.settings.bootstrap_admin_email", None)
    assert asyncio.run(_apply_bootstrap_admin_email(db, user)) is user
    assert db.commit_calls == 0

    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "other@example.com"
    )
    assert asyncio.run(_apply_bootstrap_admin_email(db, user)) is user
    assert db.commit_calls == 0

    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )
    user.is_admin = True
    assert asyncio.run(_apply_bootstrap_admin_email(db, user)) is user
    assert db.commit_calls == 0


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
