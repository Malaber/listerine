# Testing and browser e2e

## Python checks

Run the standard checks with:

```bash
pytest
black --check .
flake8 .
```

In Codex-style environments where `.codex/setup.sh` falls back to the repo virtualenv, use:

```bash
.venv/bin/pytest -q
.venv/bin/black --check .
.venv/bin/flake8 .
```

## Browser UI e2e

The CI workflow includes a seeded Playwright browser flow. It:

- starts the app with `SEED_DATA_PATH=app/fixtures/review_seed.json`
- seeds multiple households, lists, categories, checked items, and passkey-backed users
- opens the app in Chromium with Playwright
- verifies real passkey login, list interactions, websocket sync, and invite acceptance
- runs the flow twice in CI (`desktop` and `iphone`), recording video and screenshots for both under the `browser-ui-e2e` artifact

## Local review-style seeded testing

```bash
SEED_DATA_PATH=app/fixtures/review_seed.json WEBAUTHN_RP_ID=localhost uvicorn app.main:app --reload
```

Then open `http://localhost:8000/login`.

## Local browser e2e flow

Start the app:

```bash
SEED_DATA_PATH=app/fixtures/review_seed.json WEBAUTHN_RP_ID=localhost DATABASE_URL=sqlite+aiosqlite:///./tmp-ui-e2e.db PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run both desktop and iPhone flows (matching CI):

```bash
WEBAUTHN_RP_ID=localhost inv browser-e2e --base-url=http://localhost:8000 --seed-path=app/fixtures/review_seed_e2e.json --artifact-root=e2e-artifacts
```

## CI-aligned local verification order

When you want a full local pre-push pass, use this order:

1. Run `.codex/setup.sh`.
2. If setup fails with an externally managed Python error, use the existing `.venv` commands.
3. Run `pytest -q`, `black --check .`, and `flake8 .`.
4. Run the seeded browser e2e flow against a fresh temporary SQLite database.
