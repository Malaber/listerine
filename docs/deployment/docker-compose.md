# Docker Compose deployment

The published container is intended to run behind Docker Compose. For a low-traffic self-hosted deployment, SQLite is enough and keeps local and deployed behavior aligned.

## Runtime characteristics

- image example: `ghcr.io/malaber/listerine:0.1.2`
- multi-architecture image for `linux/amd64` and `linux/arm64`
- app port inside the container: `8000`
- health endpoint: `/health`
- database migrations run automatically on startup
- SQLite database path inside the container: `/data/listerine.db`
- persisted SQLite file on the host: `./data/listerine.db`

## Example `.env`

```dotenv
LISTERINE_IMAGE=ghcr.io/malaber/listerine:0.1.2
SECRET_KEY=replace-this-with-a-long-random-secret
APP_BASE_URL=https://listerine.example.com
WEBAUTHN_RP_ID=listerine.example.com
WEBCREDENTIALS_APPS=["VWKG94374J.de.malaber.listerine"]
SECURE_COOKIES=true
UVICORN_FORWARDED_ALLOW_IPS=127.0.0.1
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
```

## Example `docker-compose.yml`

```yaml
services:
  app:
    image: ${LISTERINE_IMAGE}
    restart: unless-stopped
    environment:
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: sqlite+aiosqlite:////data/listerine.db
      APP_BASE_URL: ${APP_BASE_URL}
      WEBAUTHN_RP_ID: ${WEBAUTHN_RP_ID}
      WEBCREDENTIALS_APPS: ${WEBCREDENTIALS_APPS}
      SECURE_COOKIES: ${SECURE_COOKIES}
      BOOTSTRAP_ADMIN_EMAIL: ${BOOTSTRAP_ADMIN_EMAIL}
      UVICORN_FORWARDED_ALLOW_IPS: ${UVICORN_FORWARDED_ALLOW_IPS}
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
```

## Deploy

```bash
mkdir -p data
sudo chown -R 100:101 data
docker compose pull
docker compose up -d
```

Then open `http://YOUR_HOST:8000/health` to confirm the container is healthy.

## Generate a passkey recovery link

If an account owner or admin loses their passkey, you can generate a one-time add-passkey link from the running container:

```bash
docker compose exec app python scripts/create_passkey_reset_link.py \
  --email admin@example.com \
  --base-url https://listerine.example.com
```

If you prefer to target a user by ID instead of email:

```bash
docker compose exec app python scripts/create_passkey_reset_link.py \
  --user-id 00000000-0000-0000-0000-000000000000 \
  --base-url https://listerine.example.com
```

Notes:

- `--base-url` should match the public HTTPS URL people use in the browser, not the internal container address.
- The script reads `DATABASE_URL` from the container environment by default, so you usually do not need to pass `--database-url` when using `docker compose exec`.
- The printed `/passkey-add/...` URL is single-use and expires automatically.

## Production notes

- set a strong `SECRET_KEY`
- keep `SECURE_COOKIES=true` when serving over HTTPS
- put the app behind a reverse proxy or load balancer that terminates TLS
- set `APP_BASE_URL` to the public HTTPS origin users and passkey clients reach
- set `WEBAUTHN_RP_ID` to that public hostname
- set `WEBCREDENTIALS_APPS` to a JSON array of Apple app IDs allowed to use native passkeys
- make the mounted data directory writable by the container user before first start, for example `sudo chown -R 100:101 data`
- verify `https://YOUR_HOST/.well-known/apple-app-site-association` returns the expected `webcredentials.apps` payload
- set `UVICORN_FORWARDED_ALLOW_IPS` to the IP or CIDR of your trusted proxy network
- keep `./data` on persistent storage so `./data/listerine.db` survives container replacement
- to upgrade, change `LISTERINE_IMAGE` and run `docker compose pull && docker compose up -d`
