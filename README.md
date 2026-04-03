# Listerine

Listerine is a self-hostable grocery-list backend and fallback browser UI built with FastAPI.

## Highlights

- `/api/v1` REST API with OpenAPI docs
- passkey-first auth plus browser fallback UI
- households, lists, categories, and item CRUD
- live list updates over WebSocket
- Alembic migrations and SQLAlchemy 2 async ORM
- Docker images published to GHCR
- CI coverage gate at 100%

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Open [http://localhost:8000/docs](http://localhost:8000/docs).

## Documentation

- [Documentation index](docs/README.md)
- [Getting started](docs/getting-started.md)
- [Testing and browser e2e](docs/testing.md)
- [Deployment overview](docs/deployment/README.md)
- [Docker Compose deployment](docs/deployment/docker-compose.md)
- [Webhooker deployment](docs/deployment/webhooker.md)
- [iOS starter app](ios/ListerineIOS/README.md)

## Seeded review identities

The checked-in review fixture (`app/fixtures/review_seed.json`) includes deterministic preview users:

- `listerine@schaedler.rocks` (non-admin): seeded into all households (owner/member as appropriate)
- `listerine_admin@schaedler.rocks` (admin): instance-admin only; household memberships are stripped
- `preview@example.com` and `preview-invitee@example.com` are kept for compatibility

The browser e2e flow uses a separate fixture, `app/fixtures/review_seed_e2e.json`, so the review deployment seed does not need to carry browser-private authenticator material.

## Export passkeys from a running PR instance

Use the helper script to copy passkey material from a live preview database into seed fixtures:

```bash
DATABASE_URL='sqlite:///path/to/preview.db' python scripts/export_seed_passkeys.py
```

Optional flags:

- `--email <address>` (repeatable) to limit exported users
- `--database-url <url>` to override `DATABASE_URL`

The script prints JSON containing each selected user's passkey `credential_id`, `public_key_b64`, and `sign_count`.

## Python version

This project is configured for Python 3.14 in Docker and CI.
