import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from db_utils import dispose_db, reset_db


@pytest.fixture()
def client() -> TestClient:
    asyncio.run(reset_db())
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(dispose_db())
