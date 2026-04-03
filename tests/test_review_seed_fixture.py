import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Passkey, User
from app.services.fixture_seed import ensure_seed_data
from db_utils import dispose_db, reset_db


def test_review_seed_fixture_has_unique_passkey_credentials_and_seeds() -> None:
    fixture_path = Path("app/fixtures/review_seed.json")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    users = payload["users"]
    emails = {user["email"] for user in users}

    credential_ids = [
        user["passkey"]["credential_id"] for user in users if isinstance(user.get("passkey"), dict)
    ]
    assert len(credential_ids) == len(set(credential_ids))
    assert "listerine_admin@schaedler.rocks" not in emails
    assert "listerine@schaedler.rocks" not in emails

    asyncio.run(reset_db())

    async def _assert_seeded() -> None:
        async with AsyncSessionLocal() as session:
            await ensure_seed_data(session, str(fixture_path))

            seeded_users = (
                (
                    await session.execute(
                        select(User).where(
                            User.email.in_(
                                [
                                    "preview@example.com",
                                    "preview-invitee@example.com",
                                ]
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(seeded_users) == 2

            passkeys = (
                (await session.execute(select(Passkey).order_by(Passkey.credential_id.asc())))
                .scalars()
                .all()
            )
            assert len(passkeys) >= 1

    try:
        asyncio.run(_assert_seeded())
    finally:
        asyncio.run(dispose_db())
