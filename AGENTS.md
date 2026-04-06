# AGENTS.md

## Build and test rules

Always run `.codex/setup.sh` first.

For local dependency installation and verification, prefer the repo virtualenv at `.venv`. If
`.codex/setup.sh` fails because the host Python is externally managed, continue in `.venv` instead
of stopping:

- If `.venv` does not exist yet, create it with `python3.14 -m venv .venv`.
- If `.venv/bin/inv` does not exist yet, bootstrap Invoke first with
  `.venv/bin/pip install invoke`.
- Use `.venv/bin/inv install-deps` to install the Python and Node dependencies. The install tasks
  intentionally hide successful dependency installer output and print captured logs only if a
  command fails, so do not add extra shell redirection for normal runs.
- If either bootstrap step fails because `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` points at a
  missing local certificate bundle, retry with those variables unset, for example:
  `env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE .venv/bin/pip install invoke`
  `env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE .venv/bin/inv install-deps`
- `.venv/bin/inv check-python`
- `.venv/bin/inv install-js`
- `.venv/bin/inv check-js`
- `.venv/bin/inv install-browser`
- `.venv/bin/inv check-browser-e2e`

Then run:
- `inv verify`

## Local testing workflow

Use this sequence for reliable local verification:

1. Run `.codex/setup.sh`.
2. If setup fails with an externally-managed Python error, use the existing `.venv` commands listed
   above for Python checks.
   If `.venv` does not exist, create it with `python3.14 -m venv .venv`, then install deps with
   `.venv/bin/pip install invoke` followed by `.venv/bin/inv install-deps`.
   If the bootstrap or Python dependency install fails because of a broken local CA bundle
   override, retry with `env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE`.
   Keep the shared install tasks' default quiet behavior; they suppress successful `pip`, `npm ci`,
   and Playwright install logs but still print captured output on failures.
3. Prefer the shared Invoke tasks rather than spelling out individual commands. The default
   local pre-push pass is `inv verify`, which runs the Python checks, JavaScript unit tests,
   Playwright browser dependency install, and the seeded browser e2e flow with the same task
   entrypoints CI uses.
4. Switch to Node 24 LTS before running any JavaScript tooling if you invoke lower-level commands
   directly. The Invoke tasks try `nvm use 24` automatically when `nvm` is available and fail fast
   if the active `node` major version is not 24.
5. If any production JavaScript changed under `app/web/static`, add or update the corresponding
   Node unit tests. `inv verify` runs the JavaScript tests unconditionally, which is the safest
   local check before pushing.
6. For the seeded browser e2e flow, prefer a fresh temporary SQLite database instead of reusing an
   old local file, because stale schema or stale seeded data can make the run misleading.
7. The default browser e2e Invoke task uses the same browser-private fixture CI uses:
   - `app/fixtures/review_seed_e2e.json`
8. Local WebAuthn browser checks must use `localhost`, not `127.0.0.1`, for the browser-facing
   URL and RP ID. Chromium rejects passkey auth on `127.0.0.1` with an invalid-domain security
   error even if the server is bound there.
9. For a one-command browser flow, use `inv check-browser-e2e`. It starts the app, waits for the
   healthcheck, runs `node scripts/run_ui_e2e.mjs`, and stops the app again.
10. To run only one browser form factor locally, use:
   - `inv browser-e2e-desktop`
   - `inv browser-e2e-mobile`
11. If you need the browser checks separately, use these shared tasks:
   - `inv install-browser`
   - `inv start-app`
   - `inv run-browser-e2e`
   - `inv stop-app`
12. The browser script reads the seeded account and passkey material from
   `app/fixtures/review_seed_e2e.json` by default, installs those passkeys into Chromium's virtual
   authenticator, and signs in through the normal `/login` page.
13. If you want a completely fresh manual browser run, override the database URL on start-up, for
   example:
   - `inv start-app --database-url=sqlite+aiosqlite:///./tmp-ui-e2e-manual.db`
14. `inv check-browser-e2e`, `inv browser-e2e-desktop`, `inv browser-e2e-mobile`, and `inv verify`
    stop the local app automatically after the e2e run.

This workflow is the preferred local path whenever the default setup script or host Python prevents
the normal CI-like commands from succeeding, and it is always acceptable to install dependencies in
the repo `.venv` before running verification.

## Frontend styling

- Shared web styling lives in `app/web/static/app.css`.
- The site favicon is `app/web/static/img/Favicon.png`.
- The primary logo/wordmark asset is `app/web/static/img/Listerine.png`.
- Brand color tokens are defined at the top of `app/web/static/app.css` as CSS custom properties.
- When updating the site palette, prefer changing those root tokens first so headers, buttons,
  cards, focus states, and auth screens stay in sync.
- If you update branding assets, make sure `app/web/templates/base.html` still points at the
  current favicon and logo paths.

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

## Release naming

- The release workflow uses merged PR metadata to name GitHub Releases created from `main`.
- If the PR description contains a line starting with `Release title:`, that value becomes the
  GitHub Release title.
- If `Release title:` is blank or omitted, the workflow falls back to the PR title.
- The workflow prefixes the final release title with the computed version automatically, so
  `Release title:` should not include the version number.
- Prefer setting `Release title:` in the PR description when the release should have a clearer name
  than the PR title or merge commit subject.
