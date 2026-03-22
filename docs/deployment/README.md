# Deployment

Listerine currently ships with two documented deployment paths.

## Options

- [Docker Compose deployment](docker-compose.md): one long-lived environment, typically behind Traefik or another reverse proxy
- [Webhooker deployment](webhooker.md): one production environment plus per-PR review environments managed by webhooker

## Which one to use

Use Docker Compose when you want the simplest single-instance deployment.

Use webhooker when you want:

- a long-lived production deployment
- isolated review environments per pull request
- CI-driven image publish and deployment wake hooks

## Deployment assets in this repo

- `deploy/webhooker/`: Compose templates, env defaults, and webhooker config files for the webhooker path
- `Dockerfile`: the app image build used by CI and deployments
