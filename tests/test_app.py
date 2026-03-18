import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

from webauthn.helpers import bytes_to_base64url

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models import User


async def _create_user(email: str, with_passkey: bool = True) -> UUID:
    async with AsyncSessionLocal() as session:
        user = User(
            email=email,
            password_hash="",
            display_name="User",
            passkey_credential_id=(
                bytes_to_base64url(f"cred-{uuid4()}".encode()) if with_passkey else None
            ),
            passkey_public_key=b"public-key" if with_passkey else None,
            passkey_sign_count=1 if with_passkey else 0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


def _auth_headers(client, email: str) -> dict[str, str]:
    user_id = asyncio.run(_create_user(email))
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


def test_full_flow(client) -> None:
    assert client.get("/health").status_code == 200
    assert client.get("/api").status_code == 200

    headers = _auth_headers(client, f"{uuid4()}@example.com")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

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

    category = client.post(
        f"/api/v1/households/{household_id}/categories",
        json={"name": "Produce", "color": "green"},
        headers=headers,
    ).json()

    assert (
        client.get(f"/api/v1/households/{household_id}/categories", headers=headers).status_code
        == 200
    )

    updated_category = client.patch(
        f"/api/v1/categories/{category['id']}",
        json={"name": "Dairy", "color": "blue"},
        headers=headers,
    ).json()
    assert updated_category["name"] == "Dairy"

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

    assert client.delete(f"/api/v1/categories/{category['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/lists/{list_id}", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200


def test_auth_and_access_error_paths(client) -> None:
    email = f"{uuid4()}@example.com"
    headers = _auth_headers(client, email)

    duplicate = client.post(
        "/api/v1/auth/register/options",
        json={"email": email, "display_name": "User"},
    )
    assert duplicate.status_code == 400

    bad_login = client.post("/api/v1/auth/login/options", json={"email": f"{uuid4()}@example.com"})
    assert bad_login.status_code == 404

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
    assert client.get(f"/api/v1/lists/{uuid4()}", headers=headers).status_code == 404


def test_cross_household_forbidden(client) -> None:
    h1 = _auth_headers(client, f"{uuid4()}@example.com")
    h2 = _auth_headers(client, f"{uuid4()}@example.com")

    household = client.post("/api/v1/households", json={"name": "Home"}, headers=h1).json()
    hid = household["id"]
    grocery_list = client.post(
        f"/api/v1/households/{hid}/lists", json={"name": "Private"}, headers=h1
    ).json()
    lid = grocery_list["id"]
    category = client.post(
        f"/api/v1/households/{hid}/categories",
        json={"name": "Secret", "color": "red"},
        headers=h1,
    ).json()

    assert client.get(f"/api/v1/households/{hid}", headers=h2).status_code == 403
    assert client.get(f"/api/v1/households/{hid}/lists", headers=h2).status_code == 403
    assert client.get(f"/api/v1/lists/{lid}", headers=h2).status_code == 403
    assert client.get(f"/api/v1/households/{hid}/categories", headers=h2).status_code == 403
    assert (
        client.patch(
            f"/api/v1/categories/{category['id']}", json={"name": "x"}, headers=h2
        ).status_code
        == 403
    )


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
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert register_verify.status_code == 200
    assert register_verify.json()["email"] == email

    client.post("/api/v1/auth/logout")

    login_options = client.post("/api/v1/auth/login/options", json={"email": email})
    assert login_options.status_code == 200
    assert "challenge" in login_options.json()

    login_verify = client.post(
        "/api/v1/auth/login/verify",
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert login_verify.status_code == 200
    assert "access_token" in login_verify.json()


def test_passkey_auth_error_paths(client, monkeypatch) -> None:
    email = f"{uuid4()}@example.com"

    assert (
        client.post(
            "/api/v1/auth/register/verify",
            json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/login/verify",
            json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
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
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
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
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert duplicate_verify.status_code == 400

    asyncio.run(_create_user(f"{uuid4()}@example.com"))
    login_options = client.post("/api/v1/auth/login/options", json={"email": email})
    assert login_options.status_code == 404

    email_with_passkey = f"{uuid4()}@example.com"
    user_id = asyncio.run(_create_user(email_with_passkey))
    login_options = client.post("/api/v1/auth/login/options", json={"email": email_with_passkey})
    assert login_options.status_code == 200

    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_authentication_response",
        lambda **_: (_ for _ in ()).throw(ValueError("boom")),
    )
    bad_login = client.post(
        "/api/v1/auth/login/verify",
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert bad_login.status_code == 401

    client.post("/api/v1/auth/login/options", json={"email": email_with_passkey})

    async def _remove_passkey() -> None:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user is not None
            user.passkey_public_key = None
            await session.commit()

    asyncio.run(_remove_passkey())
    missing_user_login = client.post(
        "/api/v1/auth/login/verify",
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert missing_user_login.status_code == 404


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
    assert "Sign in with passkey" in response.text
    assert "Create passkey" in response.text
    assert "Password signup and password login are disabled." in response.text
    assert "Logout" not in response.text
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/lists/abc", follow_redirects=False).status_code == 303

    script = client.get("/static/app.js")
    assert "navigator.credentials.create" in script.text
    assert "navigator.credentials.get" in script.text


def test_login_page_redirects_for_logged_in_user(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.routes.auth.verify_registration_response",
        lambda **_: _mock_verified_registration(),
    )

    email = f"{uuid4()}@example.com"
    client.post("/api/v1/auth/register/options", json={"email": email, "display_name": "User"})
    verify = client.post(
        "/api/v1/auth/register/verify",
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
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
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert verify.status_code == 200

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert 'action="/logout"' in dashboard.text
    assert ">Logout<" in dashboard.text

    list_detail = client.get("/lists/abc")
    assert list_detail.status_code == 200
    assert 'action="/logout"' in list_detail.text


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
        json={"credential": {"id": "credential-id", "type": "public-key", "response": {}}},
    )
    assert verify.status_code == 200

    logout = client.post("/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


def test_preview_page_requires_flag(client) -> None:
    assert client.get("/preview").status_code == 404
