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

## Install local dependencies

Use the shared Invoke bootstrap task to install local development dependencies:

```bash
python3.14 -m venv .venv
.venv/bin/pip install invoke
.venv/bin/inv install-deps
```

Optional flags:

- `--python-bin <python>` to choose a different Python executable for the virtualenv
- `--with-browser` to also install the Playwright Chromium bundle
- `--browser-with-deps` to use Playwright's `--with-deps` install flow when `--with-browser` is enabled

## Generate a passkey recovery link from the server

If someone loses their passkey, you can generate the same one-time add-passkey link that the admin UI creates directly from inside the Docker container:

```bash
DATABASE_URL='sqlite+aiosqlite:///./listerine.db' \
APP_BASE_URL='https://listerine.example.com' \
python scripts/create_passkey_reset_link.py --email admin@example.com
```

Optional flags:

- `--user-id <uuid>` to target a user by UUID instead of email
- `--database-url <url>` to override `DATABASE_URL`
- `--base-url <url>` to override `APP_BASE_URL`

The script prints the one-time `/passkey-add/...` URL and its expiry timestamp.

For Docker Compose deployments, you can run it directly in the live container:

```bash
docker compose exec app python scripts/create_passkey_reset_link.py \
  --email admin@example.com \
  --base-url https://listerine.example.com
```

## Python version

This project is configured for Python 3.14 in Docker and CI.
