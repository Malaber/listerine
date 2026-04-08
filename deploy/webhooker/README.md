# Listerine webhooker deployment

This directory contains the Listerine-specific deployment bundle for running
Listerine with [`webhooker`](https://github.com/Malaber/webhooker) in both
production and review mode.

The generic Ansible role is not in this repository. It is provided by the
published `malaber.webhooker` Galaxy collection from the `webhooker` repo. This
directory is what a consuming infra repo should copy into its own `files/` tree
and reference from that role.

## Included files

- `compose.production.yml`: production Compose template for one long-lived deployment
- `compose.review.yml`: review Compose template reused for each pull request
- `env/production.common.env`: non-secret production runtime defaults
- `env/review.common.env`: non-secret review runtime defaults
- `config/listerine-production.yaml`: `webhooker` project definition for production
- `config/listerine-review.yaml`: `webhooker` project definition for review deployments

## What the infra repo should do

Use the external `malaber.webhooker.webhooker` role to:

- deploy the `webhooker` stack itself
- render `/srv/listerine-pr/webhooker/env/webhooker.env`
- publish these Listerine bundle files onto the target host
- render Listerine secret env files
- add worker mounts for every Listerine host path the worker must read

In other words: this repo provides the app bundle, and the `webhooker` repo
provides the reusable deployment role.

## Suggested consuming repo layout

```text
infra-repo/
├── requirements.yml
├── inventory/
│   └── hosts.ini
├── playbooks/
│   └── deploy-webhooker.yml
├── vars/
│   ├── webhooker.yml
│   └── webhooker.secrets.yml
└── files/
    └── listerine/
        └── deploy/
            └── webhooker/
                ├── compose.production.yml
                ├── compose.review.yml
                └── env/
                    ├── production.common.env
                    └── review.common.env
```

## Install the collection in the infra repo

Example `requirements.yml`:

```yaml
---
collections:
  - name: https://github.com/Malaber/webhooker/releases/download/vX.Y.Z/malaber-webhooker-X.Y.Z.tar.gz
    type: url
```

Install:

```bash
ansible-galaxy collection install -r requirements.yml
```

## Playbook in the infra repo

```yaml
---
- name: Deploy webhooker
  hosts: webhooker_hosts
  become: true
  roles:
    - role: malaber.webhooker.webhooker
```

## Non-secret vars in the infra repo

The non-secret vars file should publish the Listerine bundle files and define
both the review and production `webhooker` projects.

Example `vars/webhooker.yml`:

```yaml
---
webhooker_image: ghcr.io/malaber/webhooker/webhooker:main

webhooker_env:
  GITHUB_TOKEN: "{{ webhooker_github_token }}"
  GITHUB_WEBHOOK_SECRET: "{{ webhooker_github_webhook_secret }}"

webhooker_worker_extra_mounts:
  - /srv/listerine-pr:/srv/listerine-pr

webhooker_managed_files:
  - src: files/listerine/deploy/webhooker/compose.review.yml
    dest: /opt/listerine/deploy/webhooker/compose.review.yml
    mode: "0644"

  - src: files/listerine/deploy/webhooker/compose.production.yml
    dest: /opt/listerine/deploy/webhooker/compose.production.yml
    mode: "0644"

  - src: files/listerine/deploy/webhooker/env/review.common.env
    dest: /opt/listerine/deploy/webhooker/env/review.common.env
    mode: "0644"

  - src: files/listerine/deploy/webhooker/env/production.common.env
    dest: /opt/listerine/deploy/webhooker/env/production.common.env
    mode: "0644"

webhooker_projects:
  - filename: listerine-review.yaml
    content:
      project_id: listerine-pr-review
      github:
        owner: Malaber
        repo: listerine
        token_env: GITHUB_TOKEN
        webhook_secret_env: GITHUB_WEBHOOK_SECRET
        required_event_types:
          - pull_request
          - ping
      deployment:
        mode: review
        compose_file: /srv/listerine-pr/deploy/compose.review.yml
        working_directory: /srv/listerine-pr/deploy
        hostname_template: pr-{pr}.pr.listerine.malaber.de
        project_name_prefix: listerine-pr-
      image:
        registry: ghcr.io
        repository: malaber/listerine
        tag_template: pr-{pr}-{sha7}
      preview:
        base_dir: /srv/listerine-pr/data/reviews
        data_dir_template: ../data/reviews/pr-{pr}/data
        sqlite_path_template: ../data/reviews/pr-{pr}/data/listerine.db
      reconcile:
        poll_interval_seconds: 60
        cleanup_closed_prs: true
        redeploy_on_sha_change: true
      traefik:
        enable_labels: true
        certresolver: letsencrypt
      state:
        state_file: /srv/listerine-pr/webhooker/runtime/state/listerine-pr-review.json
      wake:
        wake_file: /srv/listerine-pr/webhooker/runtime/wake/listerine-pr-review

  - filename: listerine-production.yaml
    content:
      project_id: listerine-production
      github:
        owner: Malaber
        repo: listerine
        token_env: GITHUB_TOKEN
        webhook_secret_env: GITHUB_WEBHOOK_SECRET
        required_event_types:
          - push
          - ping
      deployment:
        mode: production
        compose_file: /srv/listerine-pr/deploy/compose.production.yml
        working_directory: /srv/listerine-pr/deploy
        project_name_prefix: listerine-
        production_project_name: listerine
        production_hostname: listerine.malaber.de
      image:
        registry: ghcr.io
        repository: malaber/listerine
        tag_template: sha-{sha}
        production_tag_template: sha-{sha}
      production:
        branch: main
        data_dir: ../data/production/data
        sqlite_path: ../data/production/data/listerine.db
        backup_dir: ../data/production/backups
        backup_keep: 3
      reconcile:
        poll_interval_seconds: 60
        cleanup_closed_prs: false
        redeploy_on_sha_change: true
      traefik:
        enable_labels: true
        certresolver: letsencrypt
      state:
        state_file: /srv/listerine-pr/webhooker/runtime/state/listerine-production.json
      wake:
        wake_file: /srv/listerine-pr/webhooker/runtime/wake/listerine-production
```

If you deploy your own fork, update:

- `github.owner`
- `image.repository`
- hostnames and Traefik names as needed

## Secret vars in the infra repo

Example `vars/webhooker.secrets.yml`:

```yaml
---
webhooker_github_token: replace-me
webhooker_github_webhook_secret: replace-me

webhooker_secret_env_files:
  - path: /srv/listerine-pr/secrets/review.env
    mode: "0600"
    content:
      SECRET_KEY: replace-me

  - path: /srv/listerine-pr/secrets/production.env
    mode: "0600"
    content:
      SECRET_KEY: replace-me
```

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
│   ├── compose.production.yml
│   ├── data/
│   ├── backups/
│   └── env/
│       └── production.common.env
└── reviews/listerine/
    └── pr-123/
        ├── compose.review.yml
        ├── data/
        └── env/
            └── review.common.env

/var/lib/webhooker/
├── state/
└── wake/
```

The `malaber.webhooker.webhooker` role is expected to create and populate these
paths based on the vars you provide, except for any higher-level OS or Docker
installation prerequisites.

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

The worker also needs write access to the Listerine data directories referenced
by the app Compose templates, so include:

```yaml
    volumes:
      - /srv/webhooker:/srv/webhooker
```

Together, the typical worker mounts for Listerine are:

```yaml
webhooker_worker_extra_mounts:
  - /opt/listerine/deploy/webhooker:/opt/listerine/deploy/webhooker:ro
  - /etc/listerine:/etc/listerine:ro
  - /srv/webhooker:/srv/webhooker
```

## Runtime behavior

- Review deployments seed deterministic real data from `/app/app/fixtures/review_seed.json`.
- Review deployments set `APP_BASE_URL=https://pr-<PR>.pr.listerine.malaber.de`.
- Review deployments set `WEBAUTHN_RP_ID=pr.listerine.malaber.de` so one shared passkey works across all PR hosts.
- Review deployments set `WEBCREDENTIALS_APPS` to the JSON array of signed iOS app IDs allowed to use native passkeys.
- Both modes mount the host data directory at `/data` in the container and use `DATABASE_URL=sqlite+aiosqlite:////data/listerine.db`.
- The rendered `APP_DATA_DIR` should stay relative when possible, for example `./data`, so the Compose bundle remains portable with its sibling folders.
- Both modes join the external Traefik network `system_traefik_external`.
- CI publishes `sha-<full git sha>` tags on branch pushes, and PR review jobs reuse the matching `sha-<pr head sha>` image.
- CI sends signed wake requests to `webhooker` after publishing images.

## GitHub Actions settings

Set these in the app repository so CI can wake `webhooker` after image publish:

- repository variable `WEBHOOKER_REVIEW_WAKE_URL`
- repository variable `WEBHOOKER_PRODUCTION_WAKE_URL`
- repository secret `WEBHOOKER_WEBHOOK_SECRET`

The secret value must match the webhook secret environment variable used by your `webhooker-api` and `webhooker-worker` services.

Review deployments from forked pull requests are not published automatically, because GitHub does not expose package-write credentials and deployment secrets to untrusted fork workflows.

## Deployment flow

1. Install the `malaber.webhooker` collection in the infra repo.
2. Copy the bundle files from this directory into the infra repo's `files/` tree.
3. Create the playbook and vars files shown above.
4. Run:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy-webhooker.yml \
  -e @vars/webhooker.yml \
  -e @vars/webhooker.secrets.yml \
  -l webhooker_hosts
```

5. Confirm these files exist on the target host:
   - `/opt/webhooker/docker-compose.yml`
   - `/etc/webhooker/env/webhooker.env`
   - `/etc/webhooker/projects/listerine-review.yaml`
   - `/etc/webhooker/projects/listerine-production.yaml`
   - `/etc/listerine/review.secrets.env`
   - `/etc/listerine/production.secrets.env`
   - `/opt/listerine/deploy/webhooker/compose.review.yml`
   - `/opt/listerine/deploy/webhooker/compose.production.yml`
6. Confirm the `webhooker-worker` container can access:
   - `/opt/listerine/deploy/webhooker`
   - `/etc/listerine`
   - `/srv/webhooker`

## Secrets files

The secret env files are owned by the consuming infra repo, not by this app
repo. They should be rendered onto the host by `webhooker_secret_env_files`.

Typical contents:

`/etc/listerine/production.secrets.env`

```dotenv
SECRET_KEY=replace-me
```

`/etc/listerine/review.secrets.env`

```dotenv
SECRET_KEY=replace-me
```

You can add future Listerine secrets there without changing the checked-in app
bundle files in this repository.
