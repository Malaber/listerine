import asyncio

from fastapi.testclient import TestClient

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import Household, User
from app.services.preview import (
    PREVIEW_EMAIL,
    UI_E2E_LIST_NAME,
    ensure_preview_seed_data,
    ensure_ui_e2e_seed_data,
    fetch_preview_context,
    fetch_ui_e2e_context,
)
from db_utils import dispose_db, reset_db


async def _seed_preview() -> None:
    async with AsyncSessionLocal() as session:
        await ensure_preview_seed_data(session)


async def _seed_ui_e2e() -> None:
    async with AsyncSessionLocal() as session:
        await ensure_ui_e2e_seed_data(session)


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


async def _insert_non_admin_preview_user() -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            User(
                email=PREVIEW_EMAIL,
                password_hash="hash",
                display_name="Preview",
                is_admin=False,
            )
        )
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


def test_fetch_ui_e2e_context_handles_missing_states() -> None:
    asyncio.run(reset_db())

    async def _check_none() -> None:
        async with AsyncSessionLocal() as session:
            assert await fetch_ui_e2e_context(session) is None

    asyncio.run(_check_none())
    asyncio.run(_insert_user_only())
    asyncio.run(_check_none())

    asyncio.run(reset_db())
    asyncio.run(_insert_user_and_household())
    asyncio.run(_check_none())

    asyncio.run(_seed_preview())

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


def test_ui_e2e_seed_is_idempotent_and_matches_schema() -> None:
    asyncio.run(reset_db())
    asyncio.run(_seed_preview())
    asyncio.run(_seed_ui_e2e())
    asyncio.run(_seed_ui_e2e())

    async def _assert_context() -> None:
        async with AsyncSessionLocal() as session:
            context = await fetch_ui_e2e_context(session)
            assert context is not None
            assert context["user"].email == PREVIEW_EMAIL
            assert context["user"].is_admin is True
            assert context["grocery_list"].name == UI_E2E_LIST_NAME
            assert len(context["items"]) == 11
            assert len(context["category_order"]) == 10

            category_names = {category.name: category for category in context["categories"]}
            assert category_names["Backwaren"].aliases == ["Brot", "Broetchen", "Baeckerei"]
            assert category_names["Backzutaten"].aliases == ["backen"]

            items_by_name = {item.name: item for item in context["items"]}
            assert items_by_name["Brot"].checked is True
            assert items_by_name["Brot"].note == "Seeded checked duplicate"
            assert items_by_name["Loose item"].category_id is None
            assert items_by_name["Eier"].quantity_text == "10"

            ordered_category_names = [
                next(
                    category.name
                    for category in context["categories"]
                    if category.id == order.category_id
                )
                for order in context["category_order"]
            ]
            assert ordered_category_names[:4] == [
                "Konserven",
                "Milch & Eier",
                "Nudeln",
                "Reinigung",
            ]

    asyncio.run(_assert_context())
    asyncio.run(dispose_db())


def test_ui_e2e_seed_promotes_existing_preview_user_to_admin() -> None:
    asyncio.run(reset_db())
    asyncio.run(_insert_non_admin_preview_user())
    asyncio.run(_seed_ui_e2e())

    async def _assert_promoted() -> None:
        async with AsyncSessionLocal() as session:
            context = await fetch_ui_e2e_context(session)
            assert context is not None
            assert context["user"].is_admin is True

    asyncio.run(_assert_promoted())
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


def test_lifespan_seeds_ui_e2e_fixture(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings.preview_seed_data", True)
    monkeypatch.setattr("app.main.settings.preview_ui_e2e_seed_data", True)
    monkeypatch.setattr("app.web.routes.settings.preview_mode", True)
    monkeypatch.setattr("app.api.v1.routes.auth.settings.preview_mode", True)
    asyncio.run(reset_db())

    try:
        with TestClient(app):
            pass

        async def _assert_context() -> None:
            async with AsyncSessionLocal() as session:
                context = await fetch_ui_e2e_context(session)
                assert context is not None
                assert context["grocery_list"].name == UI_E2E_LIST_NAME

        asyncio.run(_assert_context())
    finally:
        monkeypatch.setattr("app.main.settings.preview_seed_data", False)
        monkeypatch.setattr("app.main.settings.preview_ui_e2e_seed_data", False)
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
