# Webhooker deployment

Listerine includes a standalone webhooker deployment bundle for one production environment and per-PR review environments.

## What lives in this repo

The deployment assets live under [`deploy/webhooker/`](../../deploy/webhooker/README.md):

- Compose templates for production and review mode
- non-secret env defaults
- webhooker project definitions
- bundle-specific host layout notes

## CI behavior

The CI workflow is wired for webhooker-managed deployments:

- pushes publish `ghcr.io/<owner>/<repo>:sha-<full git sha>`
- pull requests publish `ghcr.io/<owner>/<repo>:sha-<pr head sha>`
- pull requests also publish `ghcr.io/<owner>/<repo>:pr-<number>-<sha7>`
- pull request builds send a signed wake request to the review deployment endpoint
- pushes to `main` send a signed wake request to the production deployment endpoint

## GitHub Actions settings

Configure these in the app repository:

- repository variable `WEBHOOKER_REVIEW_WAKE_URL`
- repository variable `WEBHOOKER_PRODUCTION_WAKE_URL`
- repository secret `WEBHOOKER_WEBHOOK_SECRET`

The secret value must match the webhook secret configured for the `webhooker` API and worker services.

## Runtime behavior

- review deployments seed deterministic real data from `/app/app/fixtures/review_seed.json`
- review deployments set `WEBAUTHN_RP_ID=listerine.example.com` so one RP can work across PR subdomains
- both modes use host-mounted SQLite
- both modes join the external Traefik network `system_traefik_external`

## Important limitations

- review deployments from forked pull requests are skipped automatically because GitHub does not expose package-write credentials or deployment secrets to untrusted forks
- if you deploy a fork of this repository, update the image repository path in `deploy/webhooker/config/*.yaml`

## Next step

Follow the bundle-specific setup notes in [`deploy/webhooker/README.md`](../../deploy/webhooker/README.md) when you are ready to copy the files onto the deploy host.
