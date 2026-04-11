# Planini webhooker deployment

This directory contains the Planini-specific deployment bundle for running
Planini with [`webhooker`](https://github.com/Malaber/webhooker) in both
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
- `config/planini-production.yaml`: `webhooker` project definition for production
- `config/planini-review.yaml`: `webhooker` project definition for review deployments

## What the infra repo should do

Use the external `malaber.webhooker.webhooker` role to:

- deploy the `webhooker` stack itself
- render `/srv/planini-pr/webhooker/env/webhooker.env`
- publish these Planini bundle files onto the target host
- render Planini secret env files
- add worker mounts for every Planini host path the worker must read

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
    └── planini/
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

The non-secret vars file should publish the Planini bundle files and define
both the review and production `webhooker` projects.

Example `vars/webhooker.yml`:

```yaml
---
webhooker_image: ghcr.io/malaber/webhooker/webhooker:main

webhooker_env:
  GITHUB_TOKEN: "{{ webhooker_github_token }}"
  GITHUB_WEBHOOK_SECRET: "{{ webhooker_github_webhook_secret }}"

webhooker_worker_extra_mounts:
  - /srv/planini-pr:/srv/planini-pr

webhooker_managed_files:
  - src: files/planini/deploy/webhooker/compose.review.yml
    dest: /opt/planini/deploy/webhooker/compose.review.yml
    mode: "0644"

  - src: files/planini/deploy/webhooker/compose.production.yml
    dest: /opt/planini/deploy/webhooker/compose.production.yml
    mode: "0644"

  - src: files/planini/deploy/webhooker/env/review.common.env
    dest: /opt/planini/deploy/webhooker/env/review.common.env
    mode: "0644"

  - src: files/planini/deploy/webhooker/env/production.common.env
    dest: /opt/planini/deploy/webhooker/env/production.common.env
    mode: "0644"

webhooker_projects:
  - filename: planini-review.yaml
    content:
      project_id: planini-pr-review
      github:
        owner: Malaber
        repo: planini
        token_env: GITHUB_TOKEN
        webhook_secret_env: GITHUB_WEBHOOK_SECRET
        required_event_types:
          - pull_request
          - ping
      deployment:
        mode: review
        compose_file: /srv/planini-pr/deploy/compose.review.yml
        working_directory: /srv/planini-pr/deploy
        hostname_template: pr-{pr}.pr.planini.malaber.de
        project_name_prefix: planini-pr-
      image:
        registry: ghcr.io
        repository: malaber/planini
        tag_template: pr-{pr}-{sha7}
      preview:
        base_dir: /srv/planini-pr/data/reviews
        data_dir_template: ../data/reviews/pr-{pr}/data
        sqlite_path_template: ../data/reviews/pr-{pr}/data/planini.db
      reconcile:
        poll_interval_seconds: 60
        cleanup_closed_prs: true
        redeploy_on_sha_change: true
      traefik:
        enable_labels: true
        certresolver: letsencrypt
      state:
        state_file: /srv/planini-pr/webhooker/runtime/state/planini-pr-review.json
      wake:
        wake_file: /srv/planini-pr/webhooker/runtime/wake/planini-pr-review

  - filename: planini-production.yaml
    content:
      project_id: planini-production
      github:
        owner: Malaber
        repo: planini
        token_env: GITHUB_TOKEN
        webhook_secret_env: GITHUB_WEBHOOK_SECRET
        required_event_types:
          - push
          - ping
      deployment:
        mode: production
        compose_file: /srv/planini-pr/deploy/compose.production.yml
        working_directory: /srv/planini-pr/deploy
        project_name_prefix: planini-
        production_project_name: planini
        production_hostname: planini.malaber.de
      image:
        registry: ghcr.io
        repository: malaber/planini
        tag_template: sha-{sha}
        production_tag_template: sha-{sha}
      production:
        branch: main
        data_dir: ../data/production/data
        sqlite_path: ../data/production/data/planini.db
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
        state_file: /srv/planini-pr/webhooker/runtime/state/planini-production.json
      wake:
        wake_file: /srv/planini-pr/webhooker/runtime/wake/planini-production
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
  - path: /srv/planini-pr/secrets/review.env
    mode: "0600"
    content:
      SECRET_KEY: replace-me

  - path: /srv/planini-pr/secrets/production.env
    mode: "0600"
    content:
      SECRET_KEY: replace-me
```

## Expected host layout

```text
/opt/planini/
└── deploy/
    └── webhooker/
        ├── compose.production.yml
        ├── compose.review.yml
        ├── env/
        │   ├── production.common.env
        │   └── review.common.env
        └── config/
            ├── planini-production.yaml
            └── planini-review.yaml

/etc/planini/
├── production.secrets.env
└── review.secrets.env

/etc/webhooker/projects/
├── planini-production.yaml
└── planini-review.yaml

/srv/webhooker/
├── production/planini/
│   ├── compose.production.yml
│   ├── data/
│   ├── backups/
│   └── env/
│       └── production.common.env
└── reviews/planini/
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

## Why `/etc/planini` matters

The Planini Compose templates use `env_file` entries that point at:

- `/etc/planini/production.secrets.env`
- `/etc/planini/review.secrets.env`

Because `docker compose` is executed by the `webhooker-worker` container, the worker must be able to read those files. Add this mount to the worker service in your `webhooker` stack:

```yaml
    volumes:
      - /etc/planini:/etc/planini:ro
```

Keep the existing mount for the Planini deployment bundle as well:

```yaml
    volumes:
      - /opt/planini/deploy/webhooker:/opt/planini/deploy/webhooker:ro
```

The worker also needs write access to the Planini data directories referenced
by the app Compose templates, so include:

```yaml
    volumes:
      - /srv/webhooker:/srv/webhooker
```

Together, the typical worker mounts for Planini are:

```yaml
webhooker_worker_extra_mounts:
  - /opt/planini/deploy/webhooker:/opt/planini/deploy/webhooker:ro
  - /etc/planini:/etc/planini:ro
  - /srv/webhooker:/srv/webhooker
```

## Runtime behavior

- Review deployments seed deterministic real data from `/app/app/fixtures/review_seed.json`.
- Review deployments set `APP_BASE_URL=https://pr-<PR>.pr.planini.malaber.de`.
- Review deployments set `WEBAUTHN_RP_ID=pr.planini.malaber.de` so one shared passkey works across all PR hosts.
- Review deployments set `WEBCREDENTIALS_APPS` to the JSON array of signed iOS app IDs allowed to use native passkeys.
- Both modes mount the host data directory at `/data` in the container and use `DATABASE_URL=sqlite+aiosqlite:////data/planini.db`.
- The rendered `APP_DATA_DIR` should stay relative when possible, for example `./data`, so the Compose bundle remains portable with its sibling folders.
- Both modes join the external Traefik network `system_traefik_external`.
- CI publishes `sha-<full git sha>` tags on branch pushes, and PR review jobs reuse the matching `sha-<pr head sha>` image.
- CI sends signed wake requests to `webhooker` after publishing images.

### Shared passkey validation host

Review passkeys need one extra deployment target besides the individual PR app
hosts. The app UI still lives on `pr-<PR>.pr.planini.malaber.de`, but the iOS
Associated Domains entitlement and `WEBAUTHN_RP_ID` both point at the shared
domain `pr.planini.malaber.de`.

Because of that, `pr.planini.malaber.de` must exist as its own deployment and
serve the Apple App Site Association payload for the signed app identifier. A
simple Nginx service behind Traefik is enough:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name pr.planini.malaber.de;

    location = /.well-known/apple-app-site-association {
        default_type application/json;
        add_header Cache-Control "public, max-age=300";
        return 200 '{"webcredentials":{"apps":["VWKG94374J.de.malaber.planini"]}}';
    }

    location = /apple-app-site-association {
        default_type application/json;
        add_header Cache-Control "public, max-age=300";
        return 200 '{"webcredentials":{"apps":["VWKG94374J.de.malaber.planini"]}}';
    }

    location = /health {
        default_type application/json;
        return 200 '{"status":"ok"}';
    }

    location / {
        return 404;
    }
}
```

Before testing native iOS passkeys against review builds, confirm both of these
URLs return `200` with the expected JSON body:

- `https://pr.planini.malaber.de/.well-known/apple-app-site-association`
- `https://pr.planini.malaber.de/apple-app-site-association`

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
   - `/etc/webhooker/projects/planini-review.yaml`
   - `/etc/webhooker/projects/planini-production.yaml`
   - `/etc/planini/review.secrets.env`
   - `/etc/planini/production.secrets.env`
   - `/opt/planini/deploy/webhooker/compose.review.yml`
   - `/opt/planini/deploy/webhooker/compose.production.yml`
6. Confirm the `webhooker-worker` container can access:
   - `/opt/planini/deploy/webhooker`
   - `/etc/planini`
   - `/srv/webhooker`

## Secrets files

The secret env files are owned by the consuming infra repo, not by this app
repo. They should be rendered onto the host by `webhooker_secret_env_files`.

Typical contents:

`/etc/planini/production.secrets.env`

```dotenv
SECRET_KEY=replace-me
```

`/etc/planini/review.secrets.env`

```dotenv
SECRET_KEY=replace-me
```

You can add future Planini secrets there without changing the checked-in app
bundle files in this repository.
