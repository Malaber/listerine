import asyncio

from fastapi.testclient import TestClient

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import Household, User
from app.services.preview import PREVIEW_EMAIL, ensure_preview_seed_data, fetch_preview_context
from db_utils import dispose_db, reset_db


async def _seed_preview() -> None:
    async with AsyncSessionLocal() as session:
        await ensure_preview_seed_data(session)


async def _insert_user_only() -> None:
    async with AsyncSessionLocal() as session:
        session.add(User(email=PREVIEW_EMAIL, password_hash="hash", display_name="Preview"))
        await session.commit()


async def _insert_user_and_household() -> None:
    async with AsyncSessionLocal() as session:
        user = User(email=PREVIEW_EMAIL, password_hash="hash", display_name="Preview")
        session.add(user)
        await session.flush()
        session.add(Household(name="Preview Household", owner_user_id=user.id))
        await session.commit()


def test_preview_page_renders_seeded_data(monkeypatch) -> None:
    monkeypatch.setattr("app.web.routes.settings.preview_mode", True)
    asyncio.run(reset_db())
    asyncio.run(_seed_preview())

    with TestClient(app) as client:
        response = client.get("/preview")

    assert response.status_code == 200
    assert "Preview Household" in response.text
    assert "Weekend Shop" in response.text
    assert "Bananas" in response.text

    asyncio.run(dispose_db())


def test_preview_page_returns_503_without_seed_data(monkeypatch) -> None:
    monkeypatch.setattr("app.web.routes.settings.preview_mode", True)
    monkeypatch.setattr("app.api.v1.routes.auth.settings.preview_mode", True)
    asyncio.run(reset_db())

    with TestClient(app) as client:
        response = client.get("/preview")
        login_response = client.post("/api/v1/auth/preview/login")

    assert response.status_code == 503
    assert login_response.status_code == 503

    asyncio.run(dispose_db())


def test_fetch_preview_context_handles_missing_states() -> None:
    asyncio.run(reset_db())

    async def _check_none() -> None:
        async with AsyncSessionLocal() as session:
            assert await fetch_preview_context(session) is None

    asyncio.run(_check_none())
    asyncio.run(_insert_user_only())
    asyncio.run(_check_none())

    asyncio.run(reset_db())
    asyncio.run(_insert_user_and_household())
    asyncio.run(_check_none())

    asyncio.run(dispose_db())


def test_preview_seed_is_idempotent() -> None:
    asyncio.run(reset_db())
    asyncio.run(_seed_preview())
    asyncio.run(_seed_preview())

    async def _assert_context() -> None:
        async with AsyncSessionLocal() as session:
            context = await fetch_preview_context(session)
            assert context is not None
            assert context["user"].email == PREVIEW_EMAIL
            assert len(context["items"]) == 3

    asyncio.run(_assert_context())
    asyncio.run(dispose_db())


def test_lifespan_seeds_preview_data(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.preview_seed_data", True)
    monkeypatch.setattr("app.web.routes.settings.preview_mode", True)
    monkeypatch.setattr("app.api.v1.routes.auth.settings.preview_mode", True)
    asyncio.run(reset_db())

    try:
        with TestClient(app) as client:
            response = client.get("/preview")
            login_response = client.post("/api/v1/auth/preview/login")
        assert response.status_code == 200
        assert "preview@example.com" in response.text
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()
    finally:
        monkeypatch.setattr("app.main.settings.preview_seed_data", False)
        monkeypatch.setattr("app.web.routes.settings.preview_mode", False)
        monkeypatch.setattr("app.api.v1.routes.auth.settings.preview_mode", False)
        asyncio.run(dispose_db())


def test_preview_login_requires_flag() -> None:
    asyncio.run(reset_db())

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/preview/login")
        assert response.status_code == 404
    finally:
        asyncio.run(dispose_db())
