# Listerine

Listerine is a self-hostable grocery-list backend and fallback browser UI built with FastAPI.

## Features in this baseline

- `/api/v1` REST API with OpenAPI docs.
- Auth endpoints: passkey-only register/login/logout/me.
- Household, list, category, and item CRUD.
- List live updates over WebSocket at `/api/v1/ws/lists/{list_id}`.
- Server-rendered fallback UI pages (`/login`, `/`, `/lists/{id}`), with dashboard and list pages gated behind login.
- SQLAlchemy 2 async ORM and Alembic migration scaffold.
- Docker Compose setup with Postgres.
- CI with black, flake8, and pytest 100% coverage gate.

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs`.


## Browser UI e2e

The repo includes a seeded Playwright browser e2e flow in CI.

That flow:

- starts the app in `PREVIEW_MODE`
- auto-seeds a demo household, a second invitee user, categories, and grocery items
- opens the app in Chromium with Playwright
- verifies login gating, list interactions, websocket sync, and invite acceptance
- records browser video and screenshots into the `browser-ui-e2e` artifact

No separate screenshot-only workflow is needed.

For local preview testing:

```bash
PREVIEW_MODE=true PREVIEW_SEED_DATA=true uvicorn app.main:app --reload
```

Then open `http://localhost:8000/preview`.

For local browser UI e2e coverage:

```bash
PREVIEW_MODE=true PREVIEW_SEED_DATA=true PREVIEW_UI_E2E_SEED_DATA=true DATABASE_URL=sqlite+aiosqlite:///./tmp-ui-e2e.db PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
PREVIEW_BASE_URL=http://127.0.0.1:8000 node scripts/run_ui_e2e.mjs
```

## Run tests

```bash
pytest
```

## Environment bootstrap (recommended)

Use the repo setup script rather than ad-hoc install commands:

```bash
./scripts/setup_env.sh
```

For Codex environments, use `.codex/setup.sh` as the environment setup script.

### Network allowlist for dependency installs

If the environment is egress-restricted, allow outbound HTTPS to at least:

- `pypi.org`
- `files.pythonhosted.org`

Add any internal package registry domains your organization uses.


## Migrations

```bash
alembic upgrade head
```

## Docker Compose

```bash
docker compose up -d
```

## Deployment with Docker Compose

The published container is intended to run behind Docker Compose. For a low-traffic self-hosted deployment, SQLite is enough and keeps local and deployed behavior aligned.

- Image: `ghcr.io/malaber/listerine:0.1.2`
- Published as a multi-architecture image for both `linux/amd64` and `linux/arm64`, so Docker Desktop on Apple silicon can pull and run it natively without an emulation override
- Default app port inside the container: `8000`
- Health endpoint: `/health`
- Database migrations run automatically when the app starts
- SQLite database file inside the container: `/data/listerine.db`
- Persisted SQLite file on the host: `./data/listerine.db`

Create a deployment directory with these two files.

`.env`

```dotenv
LISTERINE_IMAGE=ghcr.io/malaber/listerine:0.1.2
SECRET_KEY=replace-this-with-a-long-random-secret
SECURE_COOKIES=true
UVICORN_FORWARDED_ALLOW_IPS=127.0.0.1
# Optional: first matching user is promoted to admin on login/register
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
```

`docker-compose.yml`

```yaml
services:
  app:
    image: ${LISTERINE_IMAGE}
    restart: unless-stopped
    environment:
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: sqlite+aiosqlite:////data/listerine.db
      SECURE_COOKIES: ${SECURE_COOKIES}
      BOOTSTRAP_ADMIN_EMAIL: ${BOOTSTRAP_ADMIN_EMAIL}
      UVICORN_FORWARDED_ALLOW_IPS: ${UVICORN_FORWARDED_ALLOW_IPS}
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

Deploy it with:

```bash
mkdir -p data
docker compose pull
docker compose up -d
```

On Apple silicon Macs, the same compose file will automatically pull the `linux/arm64` variant when it is available.

Then open `http://YOUR_HOST:8000/health` to confirm the container is healthy.

Notes for production:

- Set a strong `SECRET_KEY`. The default development value is not safe for deployment.
- Keep `SECURE_COOKIES=true` when serving over HTTPS.
- Put the app behind a reverse proxy or load balancer that terminates TLS.
- Set `UVICORN_FORWARDED_ALLOW_IPS` to the IP or CIDR of your trusted proxy network so forwarded scheme and host headers are only accepted from Traefik or another trusted proxy.
- If you intentionally want to trust any proxy source, `UVICORN_FORWARDED_ALLOW_IPS=*` is supported, but that is less strict.
- Keep the `./data` directory on persistent storage so `./data/listerine.db` survives container replacement.
- To upgrade, change `LISTERINE_IMAGE` to a newer tag such as `ghcr.io/malaber/listerine:0.1.3`, then run `docker compose pull && docker compose up -d`.

## SwiftUI client roadmap

The API contracts are stable under `/api/v1` and intentionally JSON-oriented for a future SwiftUI iOS client.


## What is the `alembic/` folder?

The `alembic/` folder contains database migration tooling and revision files.

- `alembic/env.py` wires Alembic to SQLAlchemy metadata.
- `alembic/versions/` stores versioned migration scripts (for example `0001_initial.py`).
- You run these migrations with `alembic upgrade head` to create/update DB schema predictably across environments.

## Python version

This project is configured for Python 3.14 in Docker and CI.


## iPhone SwiftUI starter app

A starter iPhone client now lives in `ios/ListerineIOS/`.

It includes:
- backend URL entry and persistence on first launch
- passkey sign-up and log-in buttons
- `AuthenticationServices`-based placeholder request creation while backend passkey endpoints are still in progress
- a Swift package test suite with a coverage gate for the iOS client core logic
- App Store release notes in `ios/ListerineIOS/README.md`
- GitHub-hosted macOS build/TestFlight workflow scaffolding for the iOS app
