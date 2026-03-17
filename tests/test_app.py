from fastapi.testclient import TestClient
from uuid import uuid4

from app.main import app


client = TestClient(app)


def test_full_flow() -> None:
    assert client.get("/health").status_code == 200
    email = f"{uuid4()}@example.com"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret", "display_name": "A"},
    )
    assert register.status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "secret"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200

    household = client.post("/api/v1/households", json={"name": "Home"}, headers=headers).json()
    household_id = household["id"]
    assert client.get(f"/api/v1/households/{household_id}", headers=headers).status_code == 200

    grocery_list = client.post(
        f"/api/v1/households/{household_id}/lists", json={"name": "Weekly"}, headers=headers
    ).json()
    list_id = grocery_list["id"]

    category = client.post(
        f"/api/v1/households/{household_id}/categories",
        json={"name": "Produce", "color": "green"},
        headers=headers,
    ).json()

    item = client.post(
        f"/api/v1/lists/{list_id}/items",
        json={"name": "Milk", "category_id": category["id"]},
        headers=headers,
    ).json()
    item_id = item["id"]

    assert client.post(f"/api/v1/items/{item_id}/check", headers=headers).json()["checked"] is True
    assert (
        client.post(f"/api/v1/items/{item_id}/uncheck", headers=headers).json()["checked"] is False
    )

    updated = client.patch(f"/api/v1/items/{item_id}", json={"note": "2%"}, headers=headers).json()
    assert updated["note"] == "2%"

    with client.websocket_connect(f"/api/v1/ws/lists/{list_id}?token={token}") as ws:
        event = ws.receive_json()
        assert event["type"] == "list_snapshot"

    assert client.delete(f"/api/v1/items/{item_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/categories/{category['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/lists/{list_id}", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200


def test_web_pages() -> None:
    assert client.get("/login").status_code == 200
    assert client.get("/").status_code == 200
    assert client.get("/lists/abc").status_code == 200
