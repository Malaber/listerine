import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from webauthn.helpers import bytes_to_base64url

from app.api.v1.routes.households import _as_utc
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models import AuthSession, HouseholdInvite, HouseholdMember, Passkey, User

REGISTERED_CREDENTIAL_ID = bytes_to_base64url(b"credential-id")
SECOND_CREDENTIAL_ID = bytes_to_base64url(b"second-credential-id")


async def _create_user(
    email: str,
    with_passkey: bool = True,
    is_admin: bool = False,
    passkey_credential_ids: list[str] | None = None,
) -> UUID:
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            password_hash="",
            display_name="User",
            is_admin=is_admin,
        )
        if with_passkey:
            credential_ids = passkey_credential_ids or [
                bytes_to_base64url(f"cred-{uuid4()}".encode())
            ]
            user.passkeys = [
                Passkey(
                    name=f"Passkey {index + 1}",
                    credential_id=credential_id,
                    public_key=b"public-key",
                    sign_count=1,
                )
                for index, credential_id in enumerate(credential_ids)
            ]
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


async def _delete_user(user_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        assert user is not None
        await session.delete(user)
        await session.commit()


async def _add_household_member(
    household_id: UUID,
    user_id: UUID,
    role: str = "member",
) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            HouseholdMember(
                household_id=household_id,
                user_id=user_id,
                role=role,
            )
        )
        await session.commit()


def _auth_headers(client, email: str, is_admin: bool = False) -> dict[str, str]:
    user_id = asyncio.run(_create_user(email, is_admin=is_admin))
    client.cookies.clear()
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _mock_verified_registration() -> SimpleNamespace:
    return SimpleNamespace(
        credential_id=b"credential-id",
        credential_public_key=b"credential-public-key",
        sign_count=1,
    )


def _mock_verified_authentication() -> SimpleNamespace:
    return SimpleNamespace(new_sign_count=2)


def _passkey_finish_payload(
    credential_id: str = REGISTERED_CREDENTIAL_ID,
) -> dict[str, object]:
    return {"credential": {"id": credential_id, "type": "public-key", "response": {}}}


def _register_session_user(client, monkeypatch, email: str) -> UUID:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "Invitee"},
    )
    response = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert response.status_code == 200
    return UUID(response.json()["id"])


def _extract_passkey_add_token_from_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    link = query["passkey_add_link"][0]
    assert "/passkey-add/" in link
    return link.rsplit("/", 1)[-1]


def _admin_user_edit_url(user_id: UUID) -> str:
    return f"/admin/user/edit/{user_id}"


def _admin_user_passkey_add_link_url(user_id: UUID) -> str:
    return f"/admin/user/{user_id}/passkey-add-link"


async def _get_auth_session(user_id: UUID) -> AuthSession | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(AuthSession).where(AuthSession.user_id == user_id))
        return result.scalar_one_or_none()


async def _set_auth_session_times(
    user_id: UUID,
    *,
    last_seen_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        auth_session = (
            await session.execute(select(AuthSession).where(AuthSession.user_id == user_id))
        ).scalar_one()
        if last_seen_at is not None:
            auth_session.last_seen_at = last_seen_at
        if expires_at is not None:
            auth_session.expires_at = expires_at
        await session.commit()


def test_full_flow(client) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/api").status_code == 200

    headers = _auth_headers(client, f"{uuid4()}@example.com")
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["is_admin"] is False

    household = client.post("/api/v1/households", json={"name": "Home"}, headers=headers).json()
    household_id = household["id"]

    assert client.get("/api/v1/households", headers=headers).status_code == 200
    assert client.get(f"/api/v1/households/{household_id}", headers=headers).status_code == 200

    grocery_list = client.post(
        f"/api/v1/households/{household_id}/lists", json={"name": "Weekly"}, headers=headers
    ).json()
    list_id = grocery_list["id"]

    assert (
        client.get(f"/api/v1/households/{household_id}/lists", headers=headers).status_code == 200
    )
    assert client.get(f"/api/v1/lists/{list_id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/lists/{list_id}/categories", headers=headers).status_code == 200

    admin_headers = _auth_headers(client, f"{uuid4()}@example.com", is_admin=True)
    category = client.post(
        "/api/v1/categories",
        json={"name": "Produce", "color": "green", "aliases": ["Veg", "Fruit & veg"]},
        headers=admin_headers,
    ).json()
    assert category["aliases"] == ["Veg", "Fruit & veg"]

    assert client.get("/api/v1/categories", headers=admin_headers).status_code == 200

    updated_category = client.patch(
        f"/api/v1/categories/{category['id']}",
        json={"name": "Dairy", "color": "blue", "aliases": ["Milk", "Cheese"]},
        headers=admin_headers,
    ).json()
    assert updated_category["name"] == "Dairy"
    assert updated_category["aliases"] == ["Milk", "Cheese"]

    bakery_category = client.post(
        "/api/v1/categories",
        json={"name": "Bakery", "color": "orange"},
        headers=admin_headers,
    ).json()

    category_order = client.put(
        f"/api/v1/lists/{list_id}/category-order",
        json={"category_ids": [bakery_category["id"], category["id"]]},
        headers=headers,
    ).json()
    assert [entry["category_id"] for entry in category_order] == [
        bakery_category["id"],
        category["id"],
    ]
    assert client.get(f"/api/v1/lists/{list_id}/category-order", headers=headers).status_code == 200

    item = client.post(
        f"/api/v1/lists/{list_id}/items",
        json={"name": "Milk", "category_id": category["id"]},
        headers=headers,
    ).json()
    item_id = item["id"]

    assert client.get(f"/api/v1/lists/{list_id}/items", headers=headers).status_code == 200

    with client.websocket_connect(
        f"/api/v1/ws/lists/{list_id}?token={headers['Authorization'][7:]}"
    ) as ws:
        event = ws.receive_json()
        assert event["type"] == "list_snapshot"
        assert [entry["category_id"] for entry in event["payload"]["category_order"]] == [
            bakery_category["id"],
            category["id"],
        ]

        reordered_categories = client.put(
            f"/api/v1/lists/{list_id}/category-order",
            json={"category_ids": [category["id"], bakery_category["id"]]},
            headers=headers,
        ).json()
        assert [entry["category_id"] for entry in reordered_categories] == [
            category["id"],
            bakery_category["id"],
        ]
        category_event = ws.receive_json()
        assert category_event["type"] == "category_order_updated"
        assert [entry["category_id"] for entry in category_event["payload"]["category_order"]] == [
            category["id"],
            bakery_category["id"],
        ]

        updated = client.patch(
            f"/api/v1/items/{item_id}",
            json={"note": "2%", "sort_order": 1},
            headers=headers,
        ).json()
        assert updated["note"] == "2%"
        assert ws.receive_json()["type"] == "item_updated"

        checked = client.post(f"/api/v1/items/{item_id}/check", headers=headers).json()
        assert checked["checked"] is True
        assert ws.receive_json()["type"] == "item_checked"

        unchecked = client.post(f"/api/v1/items/{item_id}/uncheck", headers=headers).json()
        assert unchecked["checked"] is False
        assert ws.receive_json()["type"] == "item_unchecked"

        assert client.delete(f"/api/v1/items/{item_id}", headers=headers).status_code == 200
        assert ws.receive_json()["type"] == "item_deleted"

    patched_list = client.patch(
        f"/api/v1/lists/{list_id}", json={"name": "Weekly 2"}, headers=headers
    ).json()
    assert patched_list["name"] == "Weekly 2"

    assert (
        client.delete(
            f"/api/v1/categories/{bakery_category['id']}", headers=admin_headers
        ).status_code
        == 200
    )
    assert (
        client.delete(f"/api/v1/categories/{category['id']}", headers=admin_headers).status_code
        == 200
    )
    assert client.delete(f"/api/v1/lists/{list_id}", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200


def test_login_page_renders_selected_locale_and_persists_cookie(client) -> None:
    response = client.get("/login?lang=de")

    assert response.status_code == 200
    assert 'lang="de"' in response.text
    assert "Anmelden" in response.text
    assert "listerine_locale=de" in response.headers["set-cookie"]

    follow_up = client.get("/login")
    assert follow_up.status_code == 200
    assert 'lang="de"' in follow_up.text


def test_pwa_assets_are_exposed(client) -> None:
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert 'rel="manifest" href="/manifest.webmanifest"' in login_page.text
    assert 'name="theme-color" content="#142a57"' in login_page.text
    assert 'rel="apple-touch-icon" href="/static/img/apple-touch-icon.png"' in login_page.text
    assert 'rel="stylesheet" href="/static/app.css?v=' in login_page.text
    assert 'type="module" src="/static/app.js?v=' in login_page.text

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    manifest_data = manifest.json()
    assert manifest_data["name"] == "Listerine"
    assert manifest_data["display"] == "standalone"
    assert manifest_data["start_url"] == "/"
    assert any(icon["src"] == "/static/img/pwa-192.png" for icon in manifest_data["icons"])
    assert any(icon.get("purpose") == "maskable" for icon in manifest_data["icons"])

    service_worker = client.get("/service-worker.js")
    assert service_worker.status_code == 200
    assert service_worker.headers["content-type"].startswith("application/javascript")
    assert service_worker.headers["cache-control"] == "no-cache"
    assert 'self.addEventListener("install"' in service_worker.text


def test_auth_and_access_error_paths(client) -> None:
    email = f"{uuid4()}@example.com"
    headers = _auth_headers(client, email)

    duplicate = client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
    )
    assert duplicate.status_code == 200

    bad_login = client.post("/api/v1/auth/login/options", json={})
    assert bad_login.status_code == 200

    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    )

    ghost_token = create_access_token(uuid4())
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {ghost_token}"}
        ).status_code
        == 401
    )

    household = client.post("/api/v1/households", json={"name": "Home"}, headers=headers).json()
    list_res = client.post(
        f"/api/v1/households/{household['id']}/lists",
        json={"name": "List"},
        headers=headers,
    ).json()

    assert (
        client.patch(
            f"/api/v1/lists/{list_res['id']}", json={"name": "   "}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/v1/lists/{list_res['id']}/items",
            json={"name": "Milk", "category_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 400
    )
    assert (
        client.put(
            f"/api/v1/lists/{list_res['id']}/category-order",
            json={"category_ids": [str(uuid4())]},
            headers=headers,
        ).status_code
        == 400
    )
    assert client.get(f"/api/v1/lists/{uuid4()}", headers=headers).status_code == 404


def test_list_category_order_rejects_duplicates_and_list_delete_cleans_up_orders(client) -> None:
    headers = _auth_headers(client, f"{uuid4()}@example.com")
    admin_headers = _auth_headers(client, f"{uuid4()}@example.com", is_admin=True)
    household = client.post("/api/v1/households", json={"name": "Home"}, headers=headers).json()
    grocery_list = client.post(
        f"/api/v1/households/{household['id']}/lists",
        json={"name": "Weekly"},
        headers=headers,
    ).json()
    category = client.post(
        "/api/v1/categories",
        json={"name": "Produce", "color": "#22c55e"},
        headers=admin_headers,
    ).json()

    duplicate_order = client.put(
        f"/api/v1/lists/{grocery_list['id']}/category-order",
        json={"category_ids": [category["id"], category["id"]]},
        headers=headers,
    )
    assert duplicate_order.status_code == 400

    valid_order = client.put(
        f"/api/v1/lists/{grocery_list['id']}/category-order",
        json={"category_ids": [category["id"]]},
        headers=headers,
    )
    assert valid_order.status_code == 200

    cleared_order = client.put(
        f"/api/v1/lists/{grocery_list['id']}/category-order",
        json={"category_ids": []},
        headers=headers,
    )
    assert cleared_order.status_code == 200
    assert cleared_order.json() == []

    restored_order = client.put(
        f"/api/v1/lists/{grocery_list['id']}/category-order",
        json={"category_ids": [category["id"]]},
        headers=headers,
    )
    assert restored_order.status_code == 200

    deleted_list = client.delete(f"/api/v1/lists/{grocery_list['id']}", headers=headers)
    assert deleted_list.status_code == 200


def test_list_categories_are_scoped_to_accessible_household(client) -> None:
    member_headers = _auth_headers(client, f"{uuid4()}@example.com")
    outsider_headers = _auth_headers(client, f"{uuid4()}@example.com")
    admin_headers = _auth_headers(client, f"{uuid4()}@example.com", is_admin=True)

    household = client.post(
        "/api/v1/households", json={"name": "Home"}, headers=member_headers
    ).json()
    grocery_list = client.post(
        f"/api/v1/households/{household['id']}/lists",
        json={"name": "Weekly"},
        headers=member_headers,
    ).json()
    global_category = client.post(
        "/api/v1/categories",
        json={"name": "Produce", "color": "#22c55e"},
        headers=admin_headers,
    ).json()

    categories = client.get(
        f"/api/v1/lists/{grocery_list['id']}/categories",
        headers=member_headers,
    )
    assert categories.status_code == 200
    assert categories.json() == [global_category]

    assert (
        client.get(
            f"/api/v1/lists/{grocery_list['id']}/categories",
            headers=outsider_headers,
        ).status_code
        == 403
    )


def test_delete_category_clears_item_category_and_order(client) -> None:
    headers = _auth_headers(client, f"{uuid4()}@example.com")
    admin_headers = _auth_headers(client, f"{uuid4()}@example.com", is_admin=True)
    household = client.post("/api/v1/households", json={"name": "Home"}, headers=headers).json()
    grocery_list = client.post(
        f"/api/v1/households/{household['id']}/lists",
        json={"name": "Weekly"},
        headers=headers,
    ).json()
    category = client.post(
        "/api/v1/categories",
        json={"name": "Produce", "color": "#22c55e"},
        headers=admin_headers,
    ).json()

    item = client.post(
        f"/api/v1/lists/{grocery_list['id']}/items",
        json={"name": "Apples", "category_id": category["id"]},
        headers=headers,
    ).json()
    order = client.put(
        f"/api/v1/lists/{grocery_list['id']}/category-order",
        json={"category_ids": [category["id"]]},
        headers=headers,
    )
    assert order.status_code == 200

    deleted_category = client.delete(f"/api/v1/categories/{category['id']}", headers=admin_headers)
    assert deleted_category.status_code == 200

    items = client.get(f"/api/v1/lists/{grocery_list['id']}/items", headers=headers).json()
    assert items[0]["id"] == item["id"]
    assert items[0]["category_id"] is None

    category_order = client.get(
        f"/api/v1/lists/{grocery_list['id']}/category-order", headers=headers
    )
    assert category_order.status_code == 200
    assert category_order.json() == []


def test_cross_household_forbidden(client) -> None:
    h1 = _auth_headers(client, f"{uuid4()}@example.com")
    h2 = _auth_headers(client, f"{uuid4()}@example.com")
    admin_headers = _auth_headers(client, f"{uuid4()}@example.com", is_admin=True)

    household = client.post("/api/v1/households", json={"name": "Home"}, headers=h1).json()
    hid = household["id"]
    grocery_list = client.post(
        f"/api/v1/households/{hid}/lists", json={"name": "Private"}, headers=h1
    ).json()
    lid = grocery_list["id"]
    category = client.post(
        "/api/v1/categories",
        json={"name": "Secret", "color": "red"},
        headers=admin_headers,
    ).json()

    assert client.get(f"/api/v1/households/{hid}", headers=h2).status_code == 403
    assert client.get(f"/api/v1/households/{hid}/lists", headers=h2).status_code == 403
    assert client.get(f"/api/v1/lists/{lid}", headers=h2).status_code == 403
    assert client.get("/api/v1/categories", headers=h2).status_code == 403
    assert client.post("/api/v1/categories", json={"name": "x"}, headers=h2).status_code == 403
    assert (
        client.patch(
            f"/api/v1/categories/{category['id']}",
            json={"name": "x", "color": None},
            headers=h2,
        ).status_code
        == 403
    )
    assert client.delete(f"/api/v1/categories/{category['id']}", headers=h2).status_code == 403


def test_api_role_boundaries_are_enforced(client) -> None:
    user_headers = _auth_headers(client, f"{uuid4()}@example.com")
    admin_headers = _auth_headers(client, f"{uuid4()}@example.com", is_admin=True)

    assert (
        client.post("/api/v1/households", json={"name": "Home"}, headers=admin_headers).status_code
        == 403
    )
    assert client.get("/api/v1/households", headers=admin_headers).status_code == 403
    assert client.get("/api/v1/categories", headers=user_headers).status_code == 403
    assert (
        client.post(
            "/api/v1/categories",
            json={"name": "Produce", "color": "#22c55e"},
            headers=user_headers,
        ).status_code
        == 403
    )


def test_household_invite_helpers_and_owner_accept_path(client) -> None:
    aware = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
    assert _as_utc(aware) == aware

    owner_headers = _auth_headers(client, f"{uuid4()}@example.com")
    household = client.post(
        "/api/v1/households", json={"name": "Home"}, headers=owner_headers
    ).json()

    invite_response = client.post(
        f"/api/v1/households/{household['id']}/invites",
        headers=owner_headers,
        json={},
    )
    token = invite_response.json()["invite_url"].rsplit("/", 1)[-1]

    owner_accept = client.post(
        f"/api/v1/households/invites/{token}/accept",
        headers=owner_headers,
        json={},
    )
    assert owner_accept.status_code == 200
    assert owner_accept.json()["id"] == household["id"]


def test_household_invite_flow_allows_joining_and_keeps_access_scoped(client) -> None:
    owner_headers = _auth_headers(client, f"{uuid4()}@example.com")
    recipient_headers = _auth_headers(client, f"{uuid4()}@example.com")
    outsider_headers = _auth_headers(client, f"{uuid4()}@example.com")

    household = client.post(
        "/api/v1/households", json={"name": "Home"}, headers=owner_headers
    ).json()
    grocery_list = client.post(
        f"/api/v1/households/{household['id']}/lists",
        json={"name": "Weekly"},
        headers=owner_headers,
    ).json()

    invite_response = client.post(
        f"/api/v1/households/{household['id']}/invites",
        headers=owner_headers,
        json={},
    )
    assert invite_response.status_code == 200
    invite = invite_response.json()
    token = invite["invite_url"].rsplit("/", 1)[-1]
    expires_at = datetime.fromisoformat(invite["expires_at"].replace("Z", "+00:00"))
    assert expires_at > datetime.now(UTC)
    assert expires_at <= datetime.now(UTC) + timedelta(hours=24, minutes=1)

    owner_preview = client.get(f"/api/v1/households/invites/{token}", headers=owner_headers)
    assert owner_preview.status_code == 200
    assert owner_preview.json()["already_member"] is True

    recipient_preview = client.get(f"/api/v1/households/invites/{token}", headers=recipient_headers)
    assert recipient_preview.status_code == 200
    assert recipient_preview.json()["household_name"] == "Home"
    assert recipient_preview.json()["already_member"] is False

    accept_response = client.post(
        f"/api/v1/households/invites/{token}/accept",
        headers=recipient_headers,
        json={},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["id"] == household["id"]

    assert (
        client.get(f"/api/v1/households/{household['id']}", headers=recipient_headers).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/households/{household['id']}/lists", headers=recipient_headers
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/lists/{grocery_list['id']}", headers=recipient_headers).status_code
        == 200
    )

    assert (
        client.get(f"/api/v1/households/invites/{token}", headers=outsider_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/households/invites/{token}/accept",
            headers=outsider_headers,
            json={},
        ).status_code
        == 404
    )


def test_household_invites_require_owner_and_reject_expired_tokens(client) -> None:
    owner_headers = _auth_headers(client, f"{uuid4()}@example.com")
    member_user_id = asyncio.run(_create_user(f"{uuid4()}@example.com"))
    member_headers = {"Authorization": f"Bearer {create_access_token(member_user_id)}"}

    missing_household = client.post(
        f"/api/v1/households/{uuid4()}/invites",
        headers=owner_headers,
        json={},
    )
    assert missing_household.status_code == 404

    household = client.post(
        "/api/v1/households", json={"name": "Home"}, headers=owner_headers
    ).json()
    asyncio.run(_add_household_member(UUID(household["id"]), member_user_id))

    forbidden = client.post(
        f"/api/v1/households/{household['id']}/invites",
        headers=member_headers,
        json={},
    )
    assert forbidden.status_code == 403

    invite_response = client.post(
        f"/api/v1/households/{household['id']}/invites",
        headers=owner_headers,
        json={},
    )
    token = invite_response.json()["invite_url"].rsplit("/", 1)[-1]

    async def _expire_invite() -> None:
        async with AsyncSessionLocal() as session:
            invite_result = await session.execute(
                select(HouseholdInvite).where(
                    HouseholdInvite.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
                )
            )
            invite = invite_result.scalar_one()
            invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    asyncio.run(_expire_invite())

    assert (
        client.get(f"/api/v1/households/invites/{token}", headers=member_headers).status_code == 404
    )
    assert (
        client.post(
            f"/api/v1/households/invites/{token}/accept",
            headers=member_headers,
            json={},
        ).status_code
        == 404
    )


def test_invite_web_flow_redirects_through_login(client, monkeypatch) -> None:
    owner_headers = _auth_headers(client, f"{uuid4()}@example.com")
    household = client.post(
        "/api/v1/households", json={"name": "Home"}, headers=owner_headers
    ).json()
    invite_response = client.post(
        f"/api/v1/households/{household['id']}/invites",
        headers=owner_headers,
        json={},
    )
    token = invite_response.json()["invite_url"].rsplit("/", 1)[-1]

    invite_page = client.get(f"/invite/{token}", follow_redirects=False)
    assert invite_page.status_code == 303
    assert invite_page.headers["location"] == f"/login?next=/invite/{token}"

    login_page = client.get("/login?next=//evil.example")
    assert login_page.status_code == 200
    assert 'data-next-url="/"' in login_page.text

    _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")

    authenticated_login_redirect = client.get(
        f"/login?next=/invite/{token}", follow_redirects=False
    )
    assert authenticated_login_redirect.status_code == 303
    assert authenticated_login_redirect.headers["location"] == f"/invite/{token}"

    authenticated_invite_page = client.get(f"/invite/{token}")
    assert authenticated_invite_page.status_code == 200
    assert f'data-invite-token="{token}"' in authenticated_invite_page.text


def test_passkey_register_and_login_flow(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_authentication_response",
        lambda **_: _mock_verified_authentication(),
    )

    email = f"{uuid4()}@example.com"
    register_options = client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
    )
    assert register_options.status_code == 200
    assert "challenge" in register_options.json()

    register_verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert register_verify.status_code == 200
    assert register_verify.json()["email"] == email
    assert register_verify.json()["is_admin"] is False

    client.post("/api/v1/auth/logout")

    login_options = client.post("/api/v1/auth/login/options", json={})
    assert login_options.status_code == 200
    assert "challenge" in login_options.json()

    login_verify = client.post(
        "/api/v1/auth/login/verify",
        json=_passkey_finish_payload(),
    )
    assert login_verify.status_code == 200
    assert "access_token" in login_verify.json()


def test_passkey_settings_replace_flow(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    email = f"{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
    )
    register_verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert register_verify.status_code == 200
    options = client.post("/api/v1/auth/settings/passkey/options", json={})
    assert options.status_code == 200
    assert "challenge" in options.json()
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"settings-credential-id",
            credential_public_key=b"credential-public-key",
            sign_count=9,
        ),
    )
    verify = client.post(
        "/api/v1/auth/settings/passkey/verify",
        json=_passkey_finish_payload(SECOND_CREDENTIAL_ID),
    )
    assert verify.status_code == 200
    assert verify.json()["email"] == email

    passkeys = client.get("/api/v1/auth/passkeys").json()
    assert len(passkeys) == 1
    assert passkeys[0]["name"] == "Passkey 1"


def test_passkey_settings_replace_error_paths(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    email = f"{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
    )
    register_verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert register_verify.status_code == 200

    expired = client.post(
        "/api/v1/auth/settings/passkey/verify",
        json=_passkey_finish_payload(),
    )
    assert expired.status_code == 400

    options = client.post("/api/v1/auth/settings/passkey/options", json={})
    assert options.status_code == 200

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: (_ for _ in ()).throw(Exception("bad verify")),
    )
    verify_failure = client.post(
        "/api/v1/auth/settings/passkey/verify",
        json=_passkey_finish_payload(),
    )
    assert verify_failure.status_code == 400

    options_again = client.post("/api/v1/auth/settings/passkey/options", json={})
    assert options_again.status_code == 200
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    duplicate_verify = client.post(
        "/api/v1/auth/settings/passkey/verify",
        json=_passkey_finish_payload(),
    )
    assert duplicate_verify.status_code == 400

    async def _missing_user(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.api.v1.routes.auth._load_user_with_passkeys", _missing_user)
    missing_user_options = client.post("/api/v1/auth/settings/passkey/options", json={})
    assert missing_user_options.status_code == 404
    missing_user_verify = client.post(
        "/api/v1/auth/settings/passkey/verify",
        json=_passkey_finish_payload(),
    )
    assert missing_user_verify.status_code == 404


def test_passkey_flow_uses_configured_webauthn_rp_id(client, monkeypatch) -> None:
    captured_rp_ids: list[str] = []
    captured_origins: list[str] = []
    forwarded_headers = {
        "host": "pr-77.review.example.com",
        "x-forwarded-proto": "https",
    }

    def _capture_registration(**kwargs):
        captured_rp_ids.append(kwargs["expected_rp_id"])
        captured_origins.append(kwargs["expected_origin"])
        return _mock_verified_registration()

    def _capture_authentication(**kwargs):
        captured_rp_ids.append(kwargs["expected_rp_id"])
        captured_origins.append(kwargs["expected_origin"])
        return _mock_verified_authentication()

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        _capture_registration,
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_authentication_response",
        _capture_authentication,
    )
    monkeypatch.setattr("app.api.v1.routes.auth.settings.webauthn_rp_id", "review.example.com")

    email = f"{uuid4()}@example.com"
    register_options = client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
        headers=forwarded_headers,
    )
    assert register_options.status_code == 200

    register_verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
        headers=forwarded_headers,
    )
    assert register_verify.status_code == 200

    client.post("/api/v1/auth/logout")
    login_options = client.post(
        "/api/v1/auth/login/options",
        json={},
        headers=forwarded_headers,
    )
    assert login_options.status_code == 200

    login_verify = client.post(
        "/api/v1/auth/login/verify",
        json=_passkey_finish_payload(),
        headers=forwarded_headers,
    )
    assert login_verify.status_code == 200
    assert captured_rp_ids == ["review.example.com", "review.example.com"]
    assert captured_origins == [
        "https://pr-77.review.example.com",
        "https://pr-77.review.example.com",
    ]


def test_bootstrap_admin_email_promotes_matching_user(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    email = "admin@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200
    assert verify.json()["is_admin"] is True


def test_bootstrap_admin_email_does_not_promote_other_users(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200
    assert verify.json()["is_admin"] is False


def test_passkey_auth_error_paths(client, monkeypatch) -> None:
    email = f"{uuid4()}@example.com"

    assert (
        client.post(
            "/api/v1/auth/register/verify",
            json=_passkey_finish_payload(),
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/login/verify",
            json=_passkey_finish_payload(),
        ).status_code
        == 400
    )

    register_options = client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
    )
    assert register_options.status_code == 200

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: (_ for _ in ()).throw(ValueError("boom")),
    )
    bad_register = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert bad_register.status_code == 400

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    email_taken = f"{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register/options",
        json={"email": email_taken, "display_name": "User"},
    )
    asyncio.run(_create_user(email_taken))
    duplicate_verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert duplicate_verify.status_code == 400
    assert duplicate_verify.json()["detail"] == (
        "Could not create that account. Try signing in with an existing "
        "passkey or use a different email."
    )

    asyncio.run(_create_user(f"{uuid4()}@example.com"))
    login_options = client.post("/api/v1/auth/login/options", json={})
    assert login_options.status_code == 200

    email_with_passkey = f"{uuid4()}@example.com"
    existing_credential_id = bytes_to_base64url(b"existing-credential-id")
    user_id = asyncio.run(
        _create_user(email_with_passkey, passkey_credential_ids=[existing_credential_id])
    )
    login_options = client.post("/api/v1/auth/login/options", json={})
    assert login_options.status_code == 200
    assert login_options.json()["allowCredentials"] == []

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_authentication_response",
        lambda **_: (_ for _ in ()).throw(ValueError("boom")),
    )
    bad_login = client.post(
        "/api/v1/auth/login/verify",
        json=_passkey_finish_payload(existing_credential_id),
    )
    assert bad_login.status_code == 401

    client.post("/api/v1/auth/login/options", json={})

    async def _remove_passkey() -> None:
        async with AsyncSessionLocal() as session:
            passkeys = (
                (await session.execute(select(Passkey).where(Passkey.user_id == user_id)))
                .scalars()
                .all()
            )
            for passkey in passkeys:
                await session.delete(passkey)
            await session.commit()

    asyncio.run(_remove_passkey())
    missing_user_login = client.post(
        "/api/v1/auth/login/verify",
        json=_passkey_finish_payload(existing_credential_id),
    )
    assert missing_user_login.status_code == 404


def test_passkey_registration_surfaces_generic_error_when_commit_conflicts(
    client, monkeypatch
) -> None:
    from app.api.v1.routes import auth as auth_routes

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})

    async def _raise_integrity_error(*args, **kwargs):
        raise IntegrityError("insert", {}, ValueError("duplicate"))

    monkeypatch.setattr(auth_routes.AsyncSession, "commit", _raise_integrity_error)

    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )

    assert verify.status_code == 400
    assert verify.json()["detail"] == (
        "Could not create that account. Try signing in with an existing "
        "passkey or use a different email."
    )


def test_passkey_login_reports_missing_user_for_registered_credential(client) -> None:
    from app.api.v1.routes import auth as auth_routes

    client.post("/api/v1/auth/login/options", json={})

    async def _missing_user_passkey(*args, **kwargs):
        return SimpleNamespace(
            credential_id=REGISTERED_CREDENTIAL_ID,
            public_key=b"credential-public-key",
            sign_count=1,
            user=None,
        )

    auth_loader = auth_routes._load_passkey_with_user_by_credential_id

    try:
        auth_routes._load_passkey_with_user_by_credential_id = _missing_user_passkey
        verify = client.post(
            "/api/v1/auth/login/verify",
            json=_passkey_finish_payload(),
        )
    finally:
        auth_routes._load_passkey_with_user_by_credential_id = auth_loader

    assert verify.status_code == 404
    assert verify.json()["detail"] == "No user found for that passkey"


def test_user_can_add_multiple_passkeys_and_delete_one_after_confirming_another(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_authentication_response",
        lambda **_: _mock_verified_authentication(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post("/api/v1/auth/register/verify", json=_passkey_finish_payload())
    assert verify.status_code == 200

    list_before = client.get("/api/v1/auth/passkeys")
    assert list_before.status_code == 200
    assert list_before.json()[0]["name"] == "Passkey 1"
    original_passkey_id = list_before.json()[0]["id"]

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"second-credential-id",
            credential_public_key=b"second-public-key",
            sign_count=4,
        ),
    )
    add_options = client.post(
        "/api/v1/auth/passkeys/register/options",
        json={"name": "Laptop"},
    )
    assert add_options.status_code == 200
    assert len(add_options.json()["excludeCredentials"]) == 1

    add_verify = client.post(
        "/api/v1/auth/passkeys/register/verify",
        json=_passkey_finish_payload(SECOND_CREDENTIAL_ID),
    )
    assert add_verify.status_code == 200
    assert add_verify.json()["name"] == "Laptop"
    added_passkey_id = add_verify.json()["id"]

    passkeys = client.get("/api/v1/auth/passkeys")
    assert passkeys.status_code == 200
    assert len(passkeys.json()) == 2
    assert [passkey["name"] for passkey in passkeys.json()] == ["Passkey 1", "Laptop"]

    rename_options = client.post(
        f"/api/v1/auth/passkeys/{added_passkey_id}/rename/options",
        json={"name": "Travel key"},
    )
    assert rename_options.status_code == 200
    assert len(rename_options.json()["allowCredentials"]) == 1

    rename_verify = client.post(
        f"/api/v1/auth/passkeys/{added_passkey_id}/rename/verify",
        json=_passkey_finish_payload(SECOND_CREDENTIAL_ID),
    )
    assert rename_verify.status_code == 200
    assert rename_verify.json()["name"] == "Travel key"

    delete_options = client.post(f"/api/v1/auth/passkeys/{original_passkey_id}/delete/options")
    assert delete_options.status_code == 200
    assert len(delete_options.json()["allowCredentials"]) == 1

    delete_verify = client.post(
        f"/api/v1/auth/passkeys/{original_passkey_id}/delete/verify",
        json=_passkey_finish_payload(SECOND_CREDENTIAL_ID),
    )
    assert delete_verify.status_code == 200

    final_passkeys = client.get("/api/v1/auth/passkeys")
    assert final_passkeys.status_code == 200
    assert len(final_passkeys.json()) == 1

    cannot_delete_last = client.post(
        f"/api/v1/auth/passkeys/{final_passkeys.json()[0]['id']}/delete/options"
    )
    assert cannot_delete_last.status_code == 400


def test_passkey_management_error_paths(client, monkeypatch) -> None:
    from app.api.v1.routes import auth as auth_routes

    first_credential_id = bytes_to_base64url(b"first-passkey")
    second_credential_id = bytes_to_base64url(b"second-passkey")
    email = f"{uuid4()}@example.com"
    user_id = asyncio.run(
        _create_user(
            email,
            passkey_credential_ids=[first_credential_id, second_credential_id],
        )
    )
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    initial_passkeys = client.get("/api/v1/auth/passkeys", headers=headers).json()
    first_passkey_id = initial_passkeys[0]["id"]

    login_options = client.post("/api/v1/auth/login/options", json={})
    assert login_options.status_code == 200
    missing_credential = client.post(
        "/api/v1/auth/login/verify",
        json={"credential": {"type": "public-key", "response": {}}},
    )
    assert missing_credential.status_code == 400

    client.post("/api/v1/auth/login/options", json={})
    wrong_credential = client.post(
        "/api/v1/auth/login/verify",
        json=_passkey_finish_payload(bytes_to_base64url(b"missing-passkey")),
    )
    assert wrong_credential.status_code == 404

    original_loader = auth_routes._load_user_with_passkeys

    async def _missing_user(*args, **kwargs):
        return None

    async def _delete_passkey(passkey_id: str) -> None:
        async with AsyncSessionLocal() as session:
            passkey = await session.get(Passkey, UUID(passkey_id))
            assert passkey is not None
            await session.delete(passkey)
            await session.commit()

    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", _missing_user)
    assert client.get("/api/v1/auth/passkeys", headers=headers).status_code == 404
    assert (
        client.post(
            "/api/v1/auth/passkeys/register/options",
            headers=headers,
            json={"name": "Backup key"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/auth/passkeys/{first_passkey_id}/rename/options",
            headers=headers,
            json={"name": "Renamed"},
        ).status_code
        == 404
    )
    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", original_loader)

    blank_name = client.post(
        "/api/v1/auth/passkeys/register/options",
        headers=headers,
        json={"name": "   "},
    )
    assert blank_name.status_code == 400

    too_long_name = client.post(
        "/api/v1/auth/passkeys/register/options",
        headers=headers,
        json={"name": "x" * 121},
    )
    assert too_long_name.status_code == 400

    blank_rename = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/rename/options",
        headers=headers,
        json={"name": "   "},
    )
    assert blank_rename.status_code == 400

    add_without_session = client.post(
        "/api/v1/auth/passkeys/register/verify",
        headers=headers,
        json=_passkey_finish_payload(),
    )
    assert add_without_session.status_code == 400

    rename_without_session = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/rename/verify",
        headers=headers,
        json=_passkey_finish_payload(first_credential_id),
    )
    assert rename_without_session.status_code == 400

    other_user_id = asyncio.run(_create_user(f"{uuid4()}@example.com"))
    other_headers = {"Authorization": f"Bearer {create_access_token(other_user_id)}"}
    assert (
        client.post(
            "/api/v1/auth/passkeys/register/options",
            headers=headers,
            json={"name": "Backup key"},
        ).status_code
        == 200
    )
    mismatched_user = client.post(
        "/api/v1/auth/passkeys/register/verify",
        headers=other_headers,
        json=_passkey_finish_payload(),
    )
    assert mismatched_user.status_code == 400

    assert (
        client.post(
            f"/api/v1/auth/passkeys/{first_passkey_id}/rename/options",
            headers=headers,
            json={"name": "Renamed"},
        ).status_code
        == 200
    )
    mismatched_rename_user = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/rename/verify",
        headers=other_headers,
        json=_passkey_finish_payload(first_credential_id),
    )
    assert mismatched_rename_user.status_code == 400

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"first-passkey",
            credential_public_key=b"public-key",
            sign_count=3,
        ),
    )
    assert (
        client.post(
            "/api/v1/auth/passkeys/register/options",
            headers=headers,
            json={"name": "First passkey copy"},
        ).status_code
        == 200
    )
    duplicate_add = client.post(
        "/api/v1/auth/passkeys/register/verify",
        headers=headers,
        json=_passkey_finish_payload(first_credential_id),
    )
    assert duplicate_add.status_code == 400

    passkeys = client.get("/api/v1/auth/passkeys", headers=headers).json()
    first_passkey_id = passkeys[0]["id"]

    rename_missing_target = client.post(
        f"/api/v1/auth/passkeys/{uuid4()}/rename/options",
        headers=headers,
        json={"name": "Renamed"},
    )
    assert rename_missing_target.status_code == 404

    assert (
        client.post(
            f"/api/v1/auth/passkeys/{first_passkey_id}/rename/options",
            headers=headers,
            json={"name": "Renamed"},
        ).status_code
        == 200
    )
    wrong_rename_credential = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/rename/verify",
        headers=headers,
        json=_passkey_finish_payload(second_credential_id),
    )
    assert wrong_rename_credential.status_code == 400

    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", _missing_user)
    missing_user_delete = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/delete/options",
        headers=headers,
    )
    assert missing_user_delete.status_code == 404
    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", original_loader)

    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", _missing_user)
    missing_user_rename = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/rename/verify",
        headers=headers,
        json=_passkey_finish_payload(first_credential_id),
    )
    assert missing_user_rename.status_code == 404
    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", original_loader)

    replacement_user_id = asyncio.run(
        _create_user(
            f"{uuid4()}@example.com",
            passkey_credential_ids=[bytes_to_base64url(b"rename-first")],
        )
    )
    replacement_headers = {"Authorization": f"Bearer {create_access_token(replacement_user_id)}"}
    replacement_passkey_id = client.get(
        "/api/v1/auth/passkeys", headers=replacement_headers
    ).json()[0]["id"]
    assert (
        client.post(
            f"/api/v1/auth/passkeys/{replacement_passkey_id}/rename/options",
            headers=replacement_headers,
            json={"name": "Renamed"},
        ).status_code
        == 200
    )
    asyncio.run(_delete_passkey(replacement_passkey_id))
    missing_rename_target = client.post(
        f"/api/v1/auth/passkeys/{replacement_passkey_id}/rename/verify",
        headers=replacement_headers,
        json=_passkey_finish_payload(bytes_to_base64url(b"rename-first")),
    )
    assert missing_rename_target.status_code == 404

    missing_target = client.post(
        f"/api/v1/auth/passkeys/{uuid4()}/delete/options",
        headers=headers,
    )
    assert missing_target.status_code == 404

    single_user_id = asyncio.run(
        _create_user(
            f"{uuid4()}@example.com",
            passkey_credential_ids=[bytes_to_base64url(b"only-passkey")],
        )
    )
    single_headers = {"Authorization": f"Bearer {create_access_token(single_user_id)}"}
    single_passkey_id = client.get("/api/v1/auth/passkeys", headers=single_headers).json()[0]["id"]
    assert (
        client.post(
            f"/api/v1/auth/passkeys/{single_passkey_id}/delete/options",
            headers=single_headers,
        ).status_code
        == 400
    )

    expired_delete = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/delete/verify",
        headers=headers,
        json=_passkey_finish_payload(second_credential_id),
    )
    assert expired_delete.status_code == 400

    assert (
        client.post(
            f"/api/v1/auth/passkeys/{first_passkey_id}/delete/options",
            headers=headers,
        ).status_code
        == 200
    )
    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", _missing_user)
    missing_user_during_delete = client.post(
        f"/api/v1/auth/passkeys/{first_passkey_id}/delete/verify",
        headers=headers,
        json=_passkey_finish_payload(second_credential_id),
    )
    assert missing_user_during_delete.status_code == 404
    monkeypatch.setattr(auth_routes, "_load_user_with_passkeys", original_loader)


def test_passkey_delete_verification_guards_and_duplicate_registration(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    existing_credential_user = asyncio.run(
        _create_user(f"{uuid4()}@example.com", passkey_credential_ids=[REGISTERED_CREDENTIAL_ID])
    )
    assert existing_credential_user

    duplicate_email = f"{uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register/options",
        json={"email": duplicate_email, "display_name": "User"},
    )
    duplicate_credential = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert duplicate_credential.status_code == 400

    first_credential_id = bytes_to_base64url(b"delete-first")
    second_credential_id = bytes_to_base64url(b"delete-second")
    email = f"{uuid4()}@example.com"
    user_id = asyncio.run(
        _create_user(
            email,
            passkey_credential_ids=[first_credential_id, second_credential_id],
        )
    )
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    passkeys = client.get("/api/v1/auth/passkeys", headers=headers).json()
    target_passkey_id = passkeys[0]["id"]

    async def _delete_passkey(passkey_id: str) -> None:
        async with AsyncSessionLocal() as session:
            passkey = await session.get(Passkey, UUID(passkey_id))
            assert passkey is not None
            await session.delete(passkey)
            await session.commit()

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_authentication_response",
        lambda **_: _mock_verified_authentication(),
    )

    assert (
        client.post(
            f"/api/v1/auth/passkeys/{target_passkey_id}/delete/options",
            headers=headers,
        ).status_code
        == 200
    )
    asyncio.run(_delete_passkey(target_passkey_id))
    missing_target = client.post(
        f"/api/v1/auth/passkeys/{target_passkey_id}/delete/verify",
        headers=headers,
        json=_passkey_finish_payload(second_credential_id),
    )
    assert missing_target.status_code == 404

    third_credential_id = bytes_to_base64url(b"delete-third")
    fourth_credential_id = bytes_to_base64url(b"delete-fourth")
    second_user_id = asyncio.run(
        _create_user(
            f"{uuid4()}@example.com",
            passkey_credential_ids=[third_credential_id, fourth_credential_id],
        )
    )
    second_headers = {"Authorization": f"Bearer {create_access_token(second_user_id)}"}
    second_passkeys = client.get("/api/v1/auth/passkeys", headers=second_headers).json()
    recreated_target_id = second_passkeys[0]["id"]
    recreated_other_id = second_passkeys[1]["id"]
    assert (
        client.post(
            f"/api/v1/auth/passkeys/{recreated_target_id}/delete/options",
            headers=second_headers,
        ).status_code
        == 200
    )
    asyncio.run(_delete_passkey(recreated_other_id))
    last_remaining = client.post(
        f"/api/v1/auth/passkeys/{recreated_target_id}/delete/verify",
        headers=second_headers,
        json=_passkey_finish_payload(fourth_credential_id),
    )
    assert last_remaining.status_code == 400

    fifth_credential_id = bytes_to_base64url(b"delete-fifth")
    sixth_credential_id = bytes_to_base64url(b"delete-sixth")
    user_id = asyncio.run(
        _create_user(
            f"{uuid4()}@example.com",
            passkey_credential_ids=[fifth_credential_id, sixth_credential_id],
        )
    )
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    target_passkey_id = client.get("/api/v1/auth/passkeys", headers=headers).json()[0]["id"]
    assert (
        client.post(
            f"/api/v1/auth/passkeys/{target_passkey_id}/delete/options",
            headers=headers,
        ).status_code
        == 200
    )
    same_passkey = client.post(
        f"/api/v1/auth/passkeys/{target_passkey_id}/delete/verify",
        headers=headers,
        json=_passkey_finish_payload(fifth_credential_id),
    )
    assert same_passkey.status_code == 400


def test_password_auth_endpoints_are_disabled(client) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": f"{uuid4()}@example.com", "passkey": "not-used-123", "display_name": "User"},
    )
    assert register.status_code == 400

    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"{uuid4()}@example.com", "passkey": "not-used-123"},
    )
    assert login.status_code == 400


def test_web_pages_require_login(client) -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "Sign In" in response.text
    assert "Create Account" in response.text
    assert "Sign in with passkey" in response.text
    assert (
        "Choose a passkey and your browser or password manager will identify the account for you."
        in response.text
    )
    assert "Create passkey" in response.text
    assert 'data-auth-tab-trigger="signin"' in response.text
    assert 'data-auth-tab-trigger="signup"' in response.text
    assert "Logout" not in response.text
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/settings", follow_redirects=False).status_code == 303
    assert client.get("/lists/abc", follow_redirects=False).status_code == 303

    script = client.get("/static/app.js")
    assert "navigator.credentials.create" in script.text
    assert "navigator.credentials.get" in script.text
    assert "data-auth-tab-trigger" in script.text
    assert 'typeof value.toJSON === "function"' in script.text


def test_login_page_redirects_for_logged_in_user(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200

    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_web_pages_render_for_logged_in_user(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert 'action="/logout"' in dashboard.text
    assert 'href="/settings"' in dashboard.text
    assert 'href="/admin"' not in dashboard.text
    assert ">Logout<" in dashboard.text
    assert "data-dashboard-add-toggle" in dashboard.text
    assert "data-dashboard-add-option" in dashboard.text
    assert "data-dashboard-list-group" in dashboard.text
    assert "Your passkeys" not in dashboard.text
    assert "Add another passkey" not in dashboard.text

    list_detail = client.get("/lists/abc")
    assert list_detail.status_code == 200
    assert 'action="/logout"' in list_detail.text
    assert "data-item-form-toggle" in list_detail.text
    assert "data-item-panel-overlay" in list_detail.text
    assert "data-item-edit-overlay" in list_detail.text
    assert "data-item-suggestions" in list_detail.text
    assert "danger-button" in list_detail.text
    assert "data-list-sync-status" in list_detail.text

    settings = client.get("/settings")
    assert settings.status_code == 200
    assert "Account and passkey" in settings.text
    assert "Signed in as" in settings.text
    assert "Change language" in settings.text
    assert "data-language-settings" in settings.text
    assert "Your passkeys" in settings.text
    assert "Add another passkey" in settings.text
    assert "data-passkey-list" in settings.text
    assert "Replace passkey" not in settings.text

    admin_page = client.get("/admin", follow_redirects=False)
    assert admin_page.status_code in {302, 303, 307}


def test_dashboard_redirects_to_last_opened_list(client, monkeypatch) -> None:
    _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")
    household = client.post("/api/v1/households", json={"name": "Home"}).json()
    grocery_list = client.post(
        f"/api/v1/households/{household['id']}/lists", json={"name": "Weekly"}
    ).json()

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert 'href="/?dashboard=1"' in dashboard.text

    list_detail = client.get(f"/lists/{grocery_list['id']}")
    assert list_detail.status_code == 200
    assert 'href="/?dashboard=1"' in list_detail.text

    next_open = client.get("/", follow_redirects=False)
    assert next_open.status_code == 303
    assert next_open.headers["location"] == f"/lists/{grocery_list['id']}"

    dashboard_link = client.get("/?dashboard=1", follow_redirects=False)
    assert dashboard_link.status_code == 200
    assert "data-dashboard-add-toggle" in dashboard_link.text


def test_dashboard_ignores_stale_last_opened_list(client, monkeypatch) -> None:
    _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")
    household = client.post("/api/v1/households", json={"name": "Home"}).json()
    grocery_list = client.post(
        f"/api/v1/households/{household['id']}/lists", json={"name": "Weekly"}
    ).json()

    assert client.get(f"/lists/{grocery_list['id']}").status_code == 200
    assert client.delete(f"/api/v1/lists/{grocery_list['id']}").status_code == 200

    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 200
    assert "data-dashboard-add-toggle" in dashboard.text


def test_dashboard_ignores_invalid_last_opened_list(client, monkeypatch) -> None:
    _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")

    assert client.get("/lists/not-a-list-id").status_code == 200

    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 200
    assert "data-dashboard-add-toggle" in dashboard.text


def test_web_pages_redirect_admin_user_to_admin_frontend(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200

    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 303
    assert dashboard.headers["location"] == "/admin"

    list_page = client.get("/lists/abc", follow_redirects=False)
    assert list_page.status_code == 303
    assert list_page.headers["location"] == "/admin"

    invite_page = client.get("/invite/some-token", follow_redirects=False)
    assert invite_page.status_code == 303
    assert invite_page.headers["location"] == "/admin"


def test_admin_page_shows_application_link_for_admin(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200

    response = client.get("/admin/")
    assert response.status_code == 200
    assert 'href="/"' in response.text
    assert "Go to application" in response.text
    assert "Listerine version:" in response.text
    assert "development" in response.text


def test_admin_can_generate_passkey_add_link_from_admin_frontend(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post("/api/v1/auth/register/verify", json=_passkey_finish_payload())
    assert verify.status_code == 200

    user_id = asyncio.run(_create_user("recover@example.com"))
    page = client.get(_admin_user_edit_url(user_id))
    assert page.status_code == 200
    assert "Generate add-passkey link" in page.text

    response = client.post(
        _admin_user_passkey_add_link_url(user_id),
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Add-passkey link ready for" in response.text

    token = _extract_passkey_add_token_from_url(str(response.url))

    async def _load_user() -> User:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user is not None
            return user

    user = asyncio.run(_load_user())
    assert user.passkey_reset_token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert user.passkey_reset_expires_at is not None
    expires_at = user.passkey_reset_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    assert expires_at > datetime.now(UTC) + timedelta(hours=23, minutes=59)
    assert expires_at < datetime.now(UTC) + timedelta(hours=24, minutes=1)


def test_passkey_add_link_adds_passkey_and_clears_token(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post("/api/v1/auth/register/verify", json=_passkey_finish_payload())
    assert verify.status_code == 200

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"replacement-credential-id",
            credential_public_key=b"replacement-public-key",
            sign_count=7,
        ),
    )

    target_user_id = asyncio.run(
        _create_user(
            "recover@example.com",
            passkey_credential_ids=[
                bytes_to_base64url(b"target-original-credential-id"),
                bytes_to_base64url(b"target-second-credential-id"),
            ],
        )
    )
    generate = client.post(
        _admin_user_passkey_add_link_url(target_user_id),
        follow_redirects=True,
    )
    token = _extract_passkey_add_token_from_url(str(generate.url))

    add_page = client.get(f"/passkey-add/{token}")
    assert add_page.status_code == 200
    assert 'data-passkey-add-token="' in add_page.text
    assert "recover@example.com" in add_page.text

    options = client.post(f"/api/v1/auth/passkey-add/{token}/options", json={})
    assert options.status_code == 200

    finish = client.post(
        f"/api/v1/auth/passkey-add/{token}/verify",
        json=_passkey_finish_payload(bytes_to_base64url(b"replacement-credential-id")),
    )
    assert finish.status_code == 200
    assert finish.json()["email"] == "recover@example.com"

    async def _load_user_and_passkeys() -> tuple[User, list[Passkey]]:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, target_user_id)
            assert user is not None
            result = await session.execute(select(Passkey).where(Passkey.user_id == target_user_id))
            return user, list(result.scalars())

    user, passkeys = asyncio.run(_load_user_and_passkeys())
    assert user.passkey_reset_token_hash is None
    assert user.passkey_reset_expires_at is None
    assert len(passkeys) == 3
    assert [passkey.name for passkey in passkeys] == ["Passkey 1", "Passkey 2", "Passkey 3"]
    assert passkeys[-1].credential_id == bytes_to_base64url(b"replacement-credential-id")

    assert client.post(f"/api/v1/auth/passkey-add/{token}/options", json={}).status_code == 404
    assert client.get("/", follow_redirects=False).status_code == 200


def test_admin_page_redirects_for_non_admin(client) -> None:
    _auth_headers(client, f"{uuid4()}@example.com")
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code in {302, 303, 307}
    assert response.headers["location"] == "/login"


def test_admin_passkey_add_link_action_requires_admin_session(client, monkeypatch) -> None:
    target_user_id = asyncio.run(_create_user("recover@example.com"))

    anonymous = client.get(_admin_user_edit_url(target_user_id), follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login"

    anonymous_post = client.post(
        _admin_user_passkey_add_link_url(target_user_id),
        follow_redirects=False,
    )
    assert anonymous_post.status_code == 303
    assert anonymous_post.headers["location"] == "/login"

    _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")
    non_admin = client.get(_admin_user_edit_url(target_user_id), follow_redirects=False)
    assert non_admin.status_code == 303
    assert non_admin.headers["location"] == "/"

    non_admin_post = client.post(
        _admin_user_passkey_add_link_url(target_user_id),
        follow_redirects=False,
    )
    assert non_admin_post.status_code == 303
    assert non_admin_post.headers["location"] == "/"


def test_passkey_add_link_flow_rejects_expired_or_missing_state(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post("/api/v1/auth/register/verify", json=_passkey_finish_payload())
    assert verify.status_code == 200

    target_user_id = asyncio.run(_create_user("recover@example.com"))
    generate = client.post(
        _admin_user_passkey_add_link_url(target_user_id),
        follow_redirects=True,
    )
    token = _extract_passkey_add_token_from_url(str(generate.url))

    client.cookies.clear()
    page = client.get(f"/passkey-add/{token}", follow_redirects=False)
    assert page.status_code == 200
    assert "Create another passkey" in page.text

    missing_state = client.post(
        f"/api/v1/auth/passkey-add/{token}/verify",
        json=_passkey_finish_payload(),
    )
    assert missing_state.status_code == 400
    assert missing_state.json()["detail"] == "Passkey add session expired"

    refresh_options = client.post(f"/api/v1/auth/passkey-add/{token}/options", json={})
    assert refresh_options.status_code == 200

    async def _expire_link() -> None:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, target_user_id)
            assert user is not None
            user.passkey_reset_expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

    asyncio.run(_expire_link())

    expired_verify = client.post(
        f"/api/v1/auth/passkey-add/{token}/verify",
        json=_passkey_finish_payload(),
    )
    assert expired_verify.status_code == 404
    assert expired_verify.json()["detail"] == "Passkey add link not found"

    expired_page = client.get(f"/passkey-add/{token}", follow_redirects=False)
    assert expired_page.status_code == 303
    assert expired_page.headers["location"] == "/login"
    assert client.post(f"/api/v1/auth/passkey-add/{token}/options", json={}).status_code == 404


def test_passkey_add_link_rejects_credential_registered_to_another_account(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post("/api/v1/auth/register/verify", json=_passkey_finish_payload())
    assert verify.status_code == 200

    target_user_id = asyncio.run(_create_user("recover@example.com", with_passkey=False))
    generate = client.post(
        _admin_user_passkey_add_link_url(target_user_id),
        follow_redirects=True,
    )
    token = _extract_passkey_add_token_from_url(str(generate.url))

    options = client.post(f"/api/v1/auth/passkey-add/{token}/options", json={})
    assert options.status_code == 200

    finish = client.post(
        f"/api/v1/auth/passkey-add/{token}/verify",
        json=_passkey_finish_payload(),
    )
    assert finish.status_code == 400
    assert finish.json()["detail"] == "That passkey is already registered"


def test_admin_passkey_add_link_action_redirects_to_user_list_when_user_is_missing(
    client, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )
    monkeypatch.setattr(
        "app.api.v1.routes.auth.settings.bootstrap_admin_email", "admin@example.com"
    )

    client.post(
        "/api/v1/auth/register/options",
        json={"email": "admin@example.com", "display_name": "Admin"},
    )
    verify = client.post("/api/v1/auth/register/verify", json=_passkey_finish_payload())
    assert verify.status_code == 200

    response = client.post(
        _admin_user_passkey_add_link_url(uuid4()),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/admin/user/list")


def test_login_page_localhost_hint(client) -> None:
    response = client.get("/login", headers={"host": "127.0.0.1:8000"})
    assert response.status_code == 200
    assert "open this page on <strong>localhost</strong>" in response.text


def test_web_logout_redirects_to_login(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200

    logout = client.post("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


def test_stale_web_session_redirects_to_login(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json=_passkey_finish_payload(),
    )
    assert verify.status_code == 200
    user_id = UUID(verify.json()["id"])

    asyncio.run(_delete_user(user_id))

    dashboard = client.get("/", follow_redirects=False)
    assert dashboard.status_code == 303
    assert dashboard.headers["location"] == "/login"

    login = client.get("/login")
    assert login.status_code == 200
    assert "Logout" not in login.text

    list_detail = client.get("/lists/abc", follow_redirects=False)
    assert list_detail.status_code == 303
    assert list_detail.headers["location"] == "/login"


def test_browser_session_slides_on_use(client, monkeypatch) -> None:
    user_id = _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")
    stale_last_seen = datetime.now(UTC) - timedelta(days=7)
    asyncio.run(_set_auth_session_times(user_id, last_seen_at=stale_last_seen))

    response = client.get("/")
    assert response.status_code == 200

    auth_session = asyncio.run(_get_auth_session(user_id))
    assert auth_session is not None
    assert _as_utc(auth_session.last_seen_at) > stale_last_seen


def test_idle_browser_session_redirects_to_login(client, monkeypatch) -> None:
    user_id = _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")
    asyncio.run(
        _set_auth_session_times(
            user_id,
            last_seen_at=datetime.now(UTC) - timedelta(days=29),
        )
    )

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert asyncio.run(_get_auth_session(user_id)) is None


def test_absolute_browser_session_redirects_to_login(client, monkeypatch) -> None:
    user_id = _register_session_user(client, monkeypatch, f"{uuid4()}@example.com")
    asyncio.run(
        _set_auth_session_times(
            user_id,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert asyncio.run(_get_auth_session(user_id)) is None


def test_preview_route_is_removed(client) -> None:
    assert client.get("/preview").status_code == 404
