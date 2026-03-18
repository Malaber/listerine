from uuid import uuid4

from app.core.security import create_access_token


def _auth_headers(client, email: str) -> dict[str, str]:
    passkey = "secret-passkey"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "passkey": passkey, "display_name": "User"},
    )
    assert register.status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "passkey": passkey})
    assert login.status_code == 200
    token = login.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


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
        "/api/v1/auth/register",
        json={"email": email, "passkey": "secret-passkey", "display_name": "User"},
    )
    assert duplicate.status_code == 400

    bad_login = client.post("/api/v1/auth/login", json={"email": email, "passkey": "wrong-passkey"})
    assert bad_login.status_code == 401

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


def test_web_pages_require_login(client) -> None:
    assert client.get("/login").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/lists/abc", follow_redirects=False).status_code == 303


def test_web_pages_render_for_logged_in_user(client) -> None:
    passkey = "secret-passkey"
    email = f"{uuid4()}@example.com"
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "passkey": passkey, "display_name": "User"},
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "passkey": passkey}).status_code
        == 200
    )

    assert client.get("/").status_code == 200
    assert client.get("/lists/abc").status_code == 200


def test_preview_page_requires_flag(client) -> None:
    assert client.get("/preview").status_code == 404
