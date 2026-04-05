# Testing and browser e2e

## Python checks

Run the standard checks with:

```bash
inv check-python
```

In Codex-style environments where `.codex/setup.sh` falls back to the repo virtualenv, use:

```bash
.venv/bin/inv check-python
```

To run the full local verification pass that mirrors CI task entrypoints, use:

```bash
inv verify
```

## Browser UI e2e

The CI workflow includes a seeded Playwright browser flow. It:

- starts the app with `SEED_DATA_PATH=app/fixtures/review_seed_e2e.json`
- seeds multiple households, lists, categories, checked items, and passkey-backed users
- opens the app in Chromium with Playwright
- verifies real passkey login, list interactions, websocket sync, and invite acceptance
- records browser video and screenshots into the `browser-ui-e2e` artifact

## Local review-style seeded testing

```bash
SEED_DATA_PATH=app/fixtures/review_seed.json WEBAUTHN_RP_ID=localhost uvicorn app.main:app --reload
```

Then open `http://localhost:8000/login`.

## Local browser e2e flow

Run the one-command browser flow:

```bash
inv install-browser
inv check-browser-e2e
```

If you want to control the lifecycle manually, use:

```bash
inv start-app --database-url=sqlite+aiosqlite:///./tmp-ui-e2e.db
inv run-browser-e2e
inv stop-app
```

## CI-aligned local verification order

When you want a full local pre-push pass, use this order:

1. Run `.codex/setup.sh`.
2. If setup fails with an externally managed Python error, create `.venv`, install `.[dev]`, and
   then use `.venv/bin/inv ...`.
3. Run `inv verify`.
