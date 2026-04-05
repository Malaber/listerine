# Webhooker deployment

Listerine ships the app-side bundle files needed for a `webhooker` deployment,
while the reusable Ansible role now lives in the separate
[`malaber.webhooker`](https://github.com/Malaber/webhooker) collection.

Use this deployment path when you want:

- one long-lived production deployment
- isolated review deployments for pull requests
- CI to publish images and wake `webhooker` automatically

## What lives where

This repository provides the Listerine-specific deployment bundle in
[`deploy/webhooker/`](../../deploy/webhooker/README.md):

- `compose.review.yml`
- `compose.production.yml`
- `env/review.common.env`
- `env/production.common.env`
- `config/listerine-review.yaml`
- `config/listerine-production.yaml`

The external `malaber.webhooker` collection provides the generic Ansible role
that:

- deploys `webhooker-api` and `webhooker-worker`
- renders `/etc/webhooker/env/webhooker.env`
- renders `/etc/webhooker/projects/*.yaml`
- copies app bundle files to the target host
- renders app secret env files
- adds extra worker bind mounts

No Listerine application code changes are needed for this integration. The work
on the Listerine side is:

- keep the bundle files in `deploy/webhooker/` current
- configure the consuming infra repo to publish those files with
  `malaber.webhooker.webhooker`
- configure CI wake URLs and shared webhook secret

## CI behavior

The CI workflow is already wired for `webhooker`-managed deployments:

- pushes publish `ghcr.io/<owner>/<repo>:sha-<full git sha>`
- pull request review jobs wait for the already-published `sha-<pr head sha>` image from the branch push
- pull request review jobs send a signed wake request to the review deployment endpoint
- pushes to `main` send a signed wake request to the production deployment endpoint
- pull request review jobs also update a sticky PR comment with the deterministic review URL

## GitHub Actions settings

Configure these in the Listerine repository:

- repository variable `WEBHOOKER_REVIEW_WAKE_URL`
- repository variable `WEBHOOKER_PRODUCTION_WAKE_URL`
- repository secret `WEBHOOKER_WEBHOOK_SECRET`

The secret value must match the webhook secret configured for the `webhooker`
API and worker services in the infra repo.

## Runtime behavior

- review deployments seed deterministic real data from `/app/app/fixtures/review_seed.json`
- review deployments set `WEBAUTHN_RP_ID=listerine.example.com` so one RP can work across PR subdomains
- both modes use host-mounted SQLite
- both modes join the external Traefik network `system_traefik_external`

## Review deployment layout

The intended contained host layout keeps everything for review deploys under `/srv/listerine-pr/`:

- `/srv/listerine-pr/deploy/`: Compose templates and non-secret env files
- `/srv/listerine-pr/secrets/`: runtime secret env files
- `/srv/listerine-pr/data/reviews/pr-<PR>/`: per-PR SQLite data
- `/srv/listerine-pr/webhooker/`: `webhooker` compose stack, project YAML, state, and wake files

The intended review URL for a pull request is:

- `https://pr-<PR>.pr.listerine.malaber.de`

## Consuming From An Infra Repo

The normal flow is:

1. Install `malaber.webhooker` from a GitHub Release tarball in the infra repo.
2. Copy the Listerine bundle files from `deploy/webhooker/` in this repo into the infra repo's `files/` tree.
3. Create a playbook that includes `malaber.webhooker.webhooker`.
4. Add one non-secret vars file with:
   - `webhooker_env`
   - `webhooker_projects`
   - `webhooker_managed_files`
   - `webhooker_worker_extra_mounts`
5. Add one secret vars file, usually encrypted with Ansible Vault, for:
   - `webhooker_secret_env_files`
   - secret values referenced by `webhooker_env`
6. Run the playbook against the host group that should run `webhooker`.

## Important limitations

- review deployments from forked pull requests are skipped automatically because GitHub does not expose package-write credentials or deployment secrets to untrusted forks
- if you deploy a fork of this repository, update the image repository path in `deploy/webhooker/config/*.yaml`

## Next step

Follow the detailed Listerine-specific consumption guide in
[`deploy/webhooker/README.md`](../../deploy/webhooker/README.md). It explains
exactly which files to copy into an infra repo, which host paths must exist, and
which `malaber.webhooker` variables need to be set.
