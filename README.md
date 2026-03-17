# Listerine

Listerine is a self-hostable grocery-list backend and fallback browser UI built with FastAPI.

## Features in this baseline

- `/api/v1` REST API with OpenAPI docs.
- Auth endpoints: register/login/logout/me.
- Household, list, category, and item CRUD.
- List live updates over WebSocket at `/api/v1/ws/lists/{list_id}`.
- Server-rendered fallback UI pages (`/login`, `/`, `/lists/{id}`).
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

## Run tests

```bash
pytest
```

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
