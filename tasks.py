from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any

from invoke import task


def _wait_for_health(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = subprocess.run(
            ["curl", "-fsS", url],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError(f"App never became healthy at {url} within {timeout_seconds} seconds")


def _run_ui_e2e(base_env: dict[str, str], base_url: str, artifact_dir: str, device: str) -> None:
    env = dict(base_env)
    env.update(
        {
            "PREVIEW_BASE_URL": base_url,
            "PREVIEW_ARTIFACT_DIR": artifact_dir,
        }
    )
    if device != "desktop":
        env["E2E_DEVICE"] = device
    subprocess.run(["node", "scripts/run_ui_e2e.mjs"], check=True, env=env)


@task
def browser_e2e(
    _ctx: Any,
    base_url: str = "http://localhost:8000",
    host: str = "127.0.0.1",
    port: int = 8000,
    artifact_root: str = "e2e-artifacts",
    seed_path: str = "app/fixtures/review_seed_e2e.json",
    webauthn_rp_id: str = "localhost",
    database_url: str = "sqlite+aiosqlite:///./tmp-ci-ui-e2e.db",
) -> None:
    """Run seeded browser e2e for desktop and iPhone and store artifacts per device."""
    base_env = dict(os.environ)
    base_env.update(
        {
            "E2E_SEED_PATH": seed_path,
            "SEED_DATA_PATH": seed_path,
            "WEBAUTHN_RP_ID": webauthn_rp_id,
            "DATABASE_URL": database_url,
            "PYTHONPATH": ".",
        }
    )

    with open("ui-e2e-server.log", "w", encoding="utf-8") as server_log:
        server = subprocess.Popen(
            ["uvicorn", "app.main:app", "--host", host, "--port", str(port)],
            stdout=server_log,
            stderr=subprocess.STDOUT,
            env=base_env,
        )
        try:
            _wait_for_health(f"http://{host}:{port}/health")
            _run_ui_e2e(
                base_env=base_env,
                base_url=base_url,
                artifact_dir=f"{artifact_root}/ui-e2e-desktop",
                device="desktop",
            )
            _run_ui_e2e(
                base_env=base_env,
                base_url=base_url,
                artifact_dir=f"{artifact_root}/ui-e2e-iphone",
                device="iphone",
            )
        finally:
            if server.poll() is None:
                server.send_signal(signal.SIGTERM)
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
