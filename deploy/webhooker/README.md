# Listerine webhooker deployment

This directory contains a standalone deployment bundle for running Listerine with [`webhooker`](https://github.com/Malaber/webhooker) in both production and review mode.

## Included files

- `compose.production.yml`: production Compose template for one long-lived deployment
- `compose.review.yml`: review Compose template reused for each pull request
- `env/production.common.env`: non-secret production runtime defaults
- `env/review.common.env`: non-secret review runtime defaults
- `config/listerine-production.yaml`: `webhooker` project definition for production
- `config/listerine-review.yaml`: `webhooker` project definition for review deployments

## Expected host layout

```text
/opt/listerine/
└── deploy/
    └── webhooker/
        ├── compose.production.yml
        ├── compose.review.yml
        ├── env/
        │   ├── production.common.env
        │   └── review.common.env
        └── config/
            ├── listerine-production.yaml
            └── listerine-review.yaml

/etc/listerine/
├── production.secrets.env
└── review.secrets.env

/etc/webhooker/projects/
├── listerine-production.yaml
└── listerine-review.yaml

/srv/webhooker/
├── production/listerine/
│   ├── data/
│   └── backups/
└── reviews/listerine/

/var/lib/webhooker/
├── state/
└── wake/
```

## Why `/etc/listerine` matters

The Listerine Compose templates use `env_file` entries that point at:

- `/etc/listerine/production.secrets.env`
- `/etc/listerine/review.secrets.env`

Because `docker compose` is executed by the `webhooker-worker` container, the worker must be able to read those files. Add this mount to the worker service in your `webhooker` stack:

```yaml
    volumes:
      - /etc/listerine:/etc/listerine:ro
```

Keep the existing mount for the Listerine deployment bundle as well:

```yaml
    volumes:
      - /opt/listerine/deploy/webhooker:/opt/listerine/deploy/webhooker:ro
```

## Runtime behavior

- Review deployments seed deterministic real data from `/app/app/fixtures/review_seed.json`.
- Review deployments set `WEBAUTHN_RP_ID=listerine.example.com` so the same passkey RP can work across PR subdomains.
- Both modes use SQLite on the host via `DATABASE_URL=sqlite+aiosqlite:///${APP_SQLITE_PATH}`.
- Both modes join the external Traefik network `system_traefik_external`.
- CI publishes `sha-<full git sha>` tags for normal pushes.
- CI publishes `sha-<pr head sha>` and `pr-<number>-<sha7>` tags for pull requests.
- CI sends signed wake requests to `webhooker` after publishing images.

## GitHub Actions settings

Set these in the app repository so CI can wake `webhooker` after image publish:

- repository variable `WEBHOOKER_REVIEW_WAKE_URL`
- repository variable `WEBHOOKER_PRODUCTION_WAKE_URL`
- repository secret `WEBHOOKER_WEBHOOK_SECRET`

The secret value must match the webhook secret environment variable used by your `webhooker-api` and `webhooker-worker` services.

Review deployments from forked pull requests are not published automatically, because GitHub does not expose package-write credentials and deployment secrets to untrusted fork workflows.

## Secrets files

Create these files on the host:

`/etc/listerine/production.secrets.env`

```dotenv
SECRET_KEY=replace-me
```

`/etc/listerine/review.secrets.env`

```dotenv
SECRET_KEY=replace-me
```

You can add any future Listerine secrets here without changing the `webhooker` project definitions.
