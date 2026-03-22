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
docker compose pull
docker compose up -d
```

Then open `http://YOUR_HOST:8000/health` to confirm the container is healthy.

## Production notes

- set a strong `SECRET_KEY`
- keep `SECURE_COOKIES=true` when serving over HTTPS
- put the app behind a reverse proxy or load balancer that terminates TLS
- set `UVICORN_FORWARDED_ALLOW_IPS` to the IP or CIDR of your trusted proxy network
- keep `./data` on persistent storage so `./data/listerine.db` survives container replacement
- to upgrade, change `LISTERINE_IMAGE` and run `docker compose pull && docker compose up -d`
