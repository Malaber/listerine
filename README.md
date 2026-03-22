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
pip install -e .[dev]
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

## Python version

This project is configured for Python 3.14 in Docker and CI.
