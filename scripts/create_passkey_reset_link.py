#!/usr/bin/env python3
"""Create a one-time passkey-add link for an existing user."""

from __future__ import annotations

import argparse
import asyncio
import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import User
from app.services.passkey_reset import build_passkey_add_link, issue_passkey_reset


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a one-time passkey-add link for an existing user so they can enroll "
            "a new passkey after losing access to their old one."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Database URL. Defaults to DATABASE_URL environment variable.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("APP_BASE_URL"),
        help=(
            "Public app base URL used to build the link. Defaults to APP_BASE_URL, "
            "for example https://listerine.example.com."
        ),
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--email", help="Email address of the user to reset.")
    target_group.add_argument("--user-id", help="UUID of the user to reset.")
    return parser


async def _issue_link(
    database_url: str,
    base_url: str,
    email: str | None,
    user_id: str | None,
) -> int:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            query = select(User)
            if email is not None:
                query = query.where(User.email == email)
            else:
                try:
                    parsed_user_id = UUID(user_id or "")
                except ValueError as exc:
                    raise SystemExit(f"Invalid --user-id: {user_id}") from exc
                query = query.where(User.id == parsed_user_id)

            user = (await session.execute(query)).scalar_one_or_none()
            if user is None:
                target = email or user_id or "unknown target"
                raise SystemExit(f"User not found: {target}")

            token, expires_at = await issue_passkey_reset(session, user)
            link = build_passkey_add_link(base_url, token)
    finally:
        await engine.dispose()

    print(f"Passkey add link for {user.email}:")
    print(link)
    print(f"Expires at: {expires_at.isoformat()}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("Missing --database-url (or DATABASE_URL).")
    if not args.base_url:
        raise SystemExit("Missing --base-url (or APP_BASE_URL).")

    return asyncio.run(_issue_link(args.database_url, args.base_url, args.email, args.user_id))


if __name__ == "__main__":
    raise SystemExit(main())
