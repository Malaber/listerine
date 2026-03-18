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


## Pull request preview screenshots

GitHub cannot host a persistent FastAPI staging environment by itself, but it can run a seeded browser e2e smoke flow for every pull request and attach screenshots to the workflow run.

This repo now includes a `PR Preview Screenshots` workflow that:

- starts the app in `PREVIEW_MODE`
- auto-seeds a demo account, household, categories, and grocery items
- opens the app in Chromium with Playwright
- verifies key routes render and captures screenshots
- uploads the results as the `pr-preview-screenshots` workflow artifact

To enable it in GitHub, just keep Actions enabled for the repository; no external hosting service is required for this screenshot-based PR preview flow.

For local preview testing:

```bash
PREVIEW_MODE=true PREVIEW_SEED_DATA=true uvicorn app.main:app --reload
```

Then open `http://localhost:8000/preview`.

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
docker compose up --build
```

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
