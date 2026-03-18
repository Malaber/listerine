# AGENTS.md

## Build and test rules

Always run `.codex/setup.sh` first.

If `.codex/setup.sh` fails because the host Python is externally managed, use the repo virtualenv
fallback instead of stopping:

- If `.venv` does not exist yet, create it with `python3.14 -m venv .venv`.
- If `.venv` pip commands fail because `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` points at a missing
  local certificate bundle, retry with those variables unset, for example:
  `env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE .venv/bin/pip install -e '.[dev]'`
- `.venv/bin/pytest -q`
- `.venv/bin/black --check .`
- `.venv/bin/flake8 .`

Then run:
- `pytest -q`
- `black --check .`
- `flake8 .`
- `node scripts/capture_preview_screenshots.mjs` with the same preview env vars CI uses after starting the preview app locally

## Local testing workflow

Use this sequence for reliable local verification:

1. Run `.codex/setup.sh`.
2. If setup fails with an externally-managed Python error, use the existing `.venv` commands listed
   above for Python checks.
   If `.venv` does not exist, create it with `python3.14 -m venv .venv`, then install deps with
   `.venv/bin/pip install -e '.[dev]'`.
   If pip fails because of a broken local CA bundle override, retry with
   `env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE`.
3. Run the Python checks before browser checks:
   - `pytest -q`
   - `black --check .`
   - `flake8 .`
4. For the preview screenshot flow, prefer a fresh temporary SQLite database instead of reusing
   `preview.db`, because an old file may not match the current schema.
5. Start the preview app locally with the CI-style env vars from the repo-local virtualenv.
   This has been a reliable way to bring the app up for local command-driven checks:
   - `PREVIEW_MODE=true PREVIEW_SEED_DATA=true DATABASE_URL=sqlite+aiosqlite:///./tmp-preview-check.db PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010`
6. In a separate shell, run:
   - `PREVIEW_BASE_URL=http://127.0.0.1:8010 node scripts/capture_preview_screenshots.mjs`
7. Stop the local preview server after the screenshots complete.

For the seeded browser e2e flow, use a dedicated temporary database and the UI e2e seed flag:

1. Start the preview app:
   - `PREVIEW_MODE=true PREVIEW_SEED_DATA=true PREVIEW_UI_E2E_SEED_DATA=true DATABASE_URL=sqlite+aiosqlite:///./tmp-ui-e2e-manual.db PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
2. In a separate shell, run:
   - `PREVIEW_BASE_URL=http://127.0.0.1:8000 node scripts/run_ui_e2e.mjs`
3. If you want a completely fresh run, delete `tmp-ui-e2e-manual.db` before restarting the server.
4. Stop the preview server after the e2e run completes.

This workflow is the preferred fallback whenever the default setup script or an old local preview
database prevents the normal CI-like commands from succeeding.


## Testing expectations

- Test coverage must remain at 100%.
- Any new Python code must include automated tests that exercise the new behavior and keep coverage at 100%.
- Before pushing, run all local checks that correspond to CI jobs and fix any failures first.

## Failure handling

- If dependency installation fails, try a reasonable fallback (for example: retry once, try alternate Python path, or run checks that do not require missing deps).
- If baseline tests cannot be executed due environment limitations, continue with the requested code fix and document the exact blocker and command output.
- Prefer meaningful progress over no-op responses when the user explicitly asks for changes.

## PR policy

A PR may be created when either:
- dependencies installed successfully and relevant tests pass, or
- environment limitations prevent running all checks, but:
  - attempted commands are listed,
  - failures are clearly identified as environment-related,
  - and code changes are scoped to the requested fix.
