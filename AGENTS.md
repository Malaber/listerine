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
- `nvm use` or otherwise switch to Node 24 LTS first
- `npm install`
- `npm run test:js`
- `npm install --no-save playwright`
- `npx playwright install chromium`
- `node scripts/run_ui_e2e.mjs` with the same seeded real-auth env vars CI uses after starting the app locally

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
4. Switch to Node 24 LTS before running any JavaScript tooling. The repo pins this via `.nvmrc`,
   `.node-version`, CI, and `package.json` engines.
5. If any production JavaScript changed under `app/web/static`, run the JavaScript unit tests:
   - To check committed production JS changes against main: `git diff --name-only origin/main...HEAD -- 'app/web/static/*.js'`
   - To check local unstaged and staged production JS changes: `git diff --name-only -- 'app/web/static/*.js'` and `git diff --cached --name-only -- 'app/web/static/*.js'`
   - If any of those commands print a production JS path, add or update the corresponding Node unit tests and run `npm run test:js`
6. For the seeded browser e2e flow, prefer a fresh temporary SQLite database instead of reusing an
   old local file, because stale schema or stale seeded data can make the run misleading.
7. Use the checked-in review seed fixture for browser e2e runs:
   - `app/fixtures/review_seed.json`
8. Local WebAuthn browser checks must use `localhost`, not `127.0.0.1`, for the browser-facing
   URL and RP ID. Chromium rejects passkey auth on `127.0.0.1` with an invalid-domain security
   error even if the server is bound there.
9. Start the app locally with a dedicated temporary database and the seeded real-auth env vars:
   - `SEED_DATA_PATH=app/fixtures/review_seed.json WEBAUTHN_RP_ID=localhost DATABASE_URL=sqlite+aiosqlite:///./tmp-ui-e2e-manual.db PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
10. In a separate shell, switch to Node 24 and install the browser dependency if needed:
   - `nvm use 24`
   - `npm install --no-save playwright`
   - `npx playwright install chromium`
11. Run the browser e2e flow against the normal login and dashboard routes:
   - `PREVIEW_BASE_URL=http://localhost:8000 WEBAUTHN_RP_ID=localhost node scripts/run_ui_e2e.mjs`
12. The browser script reads the seeded account and passkey material from
   `app/fixtures/review_seed.json`, installs those passkeys into Chromium's virtual authenticator,
   and signs in through the normal `/login` page.
13. If you want a completely fresh run, delete `tmp-ui-e2e-manual.db` before restarting the app.
14. Stop the local app after the e2e run completes.

This workflow is the preferred fallback whenever the default setup script or an old local database
prevents the normal CI-like commands from succeeding.


## Testing expectations

- Test coverage must remain at 100%.
- Any new Python code must include automated tests that exercise the new behavior and keep coverage at 100%.
- Any new or changed production JavaScript in `app/web/static` must include unit tests, and JavaScript coverage must remain at 100%.
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
