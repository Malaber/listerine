from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

try:
    from invoke import task
    from invoke.exceptions import Exit
except ModuleNotFoundError:  # pragma: no cover - bootstrap fallback before dev deps are installed.

    class Exit(RuntimeError):
        pass

    def task(*args, **kwargs):
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def decorator(func):
            return func

        return decorator


ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_HEALTH_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health"
DEFAULT_PREVIEW_BASE_URL = "http://localhost:8000"
DEFAULT_BROWSER_SEED_PATH = "app/fixtures/review_seed_e2e.json"
DEFAULT_BROWSER_DATABASE_URL = "sqlite+aiosqlite:///./tmp-ui-e2e-invoke.db"
DEFAULT_APP_LOG_PATH = "ui-e2e-server.log"
DEFAULT_APP_PID_PATH = "ui-e2e-server.pid"


def _tool_path(name: str) -> str:
    current_bin = Path(sys.executable).resolve().parent / name
    if current_bin.exists():
        return str(current_bin)

    local_bin = ROOT / ".venv" / "bin" / name
    if local_bin.exists():
        return str(local_bin)

    return name


def _python_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env.update({key: value for key, value in overrides.items() if value is not None})
    return env


def _pip_env() -> dict[str, str]:
    env = os.environ.copy()
    for var_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        value = env.get(var_name)
        if value and not Path(value).exists():
            env.pop(var_name, None)
    return env


def _node_bootstrap() -> str:
    version_check = (
        "node -e \"const major = Number(process.versions.node.split('.')[0]); "
        "if (major !== 24) { "
        "console.error('Node 24.x is required. Run `nvm use 24` or equivalent first.'); "
        "process.exit(1); "
        '}"'
    )
    return (
        'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
        'source "$HOME/.nvm/nvm.sh" && nvm use 24 >/dev/null; '
        "fi && "
        f"{version_check}"
    )


def _node_command(command: str) -> str:
    return f"{_node_bootstrap()} && {command}"


def _black_command(*args: str) -> str:
    return " ".join([shlex.quote(_tool_path("black")), *args])


def _app_env(
    *,
    seed_path: str,
    database_url: str,
    webauthn_rp_id: str,
) -> dict[str, str]:
    return _python_env(
        SEED_DATA_PATH=seed_path,
        DATABASE_URL=database_url,
        WEBAUTHN_RP_ID=webauthn_rp_id,
    )


def _wait_for_healthcheck(url: str, attempts: int, sleep_seconds: float) -> None:
    last_error = ""
    for _ in range(attempts):
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return
                last_error = f"unexpected status {response.status}"
        except URLError as exc:
            last_error = str(exc)
        time.sleep(sleep_seconds)
    raise Exit(f"App never became healthy at {url}: {last_error}")


def _read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    contents = pid_path.read_text(encoding="utf-8").strip()
    return int(contents) if contents else None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@task
def setup(c) -> None:
    c.run("./scripts/setup_env.sh", pty=False, shell="/bin/bash")


@task(help={"python_bin": "Python executable to use when creating the repo virtualenv."})
def setup_venv(c, python_bin="python3.14") -> None:
    venv_dir = ROOT / ".venv"
    if not venv_dir.exists():
        c.run(f"{shlex.quote(python_bin)} -m venv .venv", pty=False, shell="/bin/bash")

    pip_path = ROOT / ".venv" / "bin" / "pip"
    c.run(
        f"{shlex.quote(str(pip_path))} install -e '.[dev]'",
        env=_pip_env(),
        pty=False,
        shell="/bin/bash",
    )


@task
def lint_python(c) -> None:
    c.run(_black_command("--check", "."), env=_python_env(), pty=False)
    c.run(f"{shlex.quote(_tool_path('flake8'))} .", env=_python_env(), pty=False)


@task
def test_python(c) -> None:
    c.run(f"{shlex.quote(_tool_path('pytest'))} -q", env=_python_env(), pty=False)


@task
def format_python(c) -> None:
    c.run(_black_command("."), env=_python_env(), pty=False)


@task(pre=[lint_python, test_python])
def check_python(c) -> None:
    """Run the Python lint and test checks."""


@task
def install_js(c) -> None:
    c.run(_node_command("npm ci"), pty=False, shell="/bin/bash")


@task
def check_js(c) -> None:
    c.run(_node_command("npm run test:js"), pty=False, shell="/bin/bash")


@task(help={"with_deps": "Use Playwright's system dependency install flow."})
def install_browser(c, with_deps=False) -> None:
    playwright_install = "npx --yes playwright install chromium"
    if with_deps:
        playwright_install = "npx --yes playwright install --with-deps chromium"

    c.run(_node_command(playwright_install), pty=False, shell="/bin/bash")


@task(
    help={
        "seed_path": "Fixture used to seed the local app database.",
        "database_url": "Database URL for the temporary local app.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the browser.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def start_app(
    c,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_BROWSER_DATABASE_URL,
    webauthn_rp_id="localhost",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    log_path=DEFAULT_APP_LOG_PATH,
    pid_path=DEFAULT_APP_PID_PATH,
) -> None:
    pid_file = ROOT / pid_path
    existing_pid = _read_pid(pid_file)
    if existing_pid is not None:
        if _pid_is_running(existing_pid):
            raise Exit(f"Refusing to start a second app instance while {pid_path} already exists.")
        pid_file.unlink(missing_ok=True)

    log_file = ROOT / log_path
    log_file.parent.mkdir(parents=True, exist_ok=True)
    env = _app_env(
        seed_path=seed_path,
        database_url=database_url,
        webauthn_rp_id=webauthn_rp_id,
    )
    with log_file.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [
                _tool_path("uvicorn"),
                "app.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pid_file.write_text(f"{process.pid}\n", encoding="utf-8")


@task(help={"pid_path": "PID file created by start-app."})
def stop_app(c, pid_path=DEFAULT_APP_PID_PATH) -> None:
    pid_file = ROOT / pid_path
    pid = _read_pid(pid_file)
    if pid is None:
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    finally:
        pid_file.unlink(missing_ok=True)


@task(
    help={
        "url": "Healthcheck URL to poll before running browser checks.",
        "attempts": "Number of healthcheck polls before failing.",
        "sleep_seconds": "Delay between healthcheck polls.",
    }
)
def wait_for_app(c, url=DEFAULT_HEALTH_URL, attempts=30, sleep_seconds=1.0) -> None:
    _wait_for_healthcheck(url=url, attempts=int(attempts), sleep_seconds=float(sleep_seconds))


@task(
    help={
        "preview_base_url": "Browser-facing base URL used by the Playwright flow.",
        "e2e_seed_path": "Fixture that contains passkey data for the browser flow.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the browser.",
    }
)
def run_browser_e2e(
    c,
    preview_base_url=DEFAULT_PREVIEW_BASE_URL,
    e2e_seed_path=DEFAULT_BROWSER_SEED_PATH,
    webauthn_rp_id="localhost",
) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PREVIEW_BASE_URL": preview_base_url,
            "E2E_SEED_PATH": e2e_seed_path,
            "WEBAUTHN_RP_ID": webauthn_rp_id,
        }
    )
    c.run(_node_command("node scripts/run_ui_e2e.mjs"), env=env, pty=False, shell="/bin/bash")


@task(
    help={
        "seed_path": "Fixture used to seed the local app database.",
        "e2e_seed_path": "Fixture that contains passkey data for the browser flow.",
        "database_url": "Database URL for the temporary local app.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the browser.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def check_browser_e2e(
    c,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    e2e_seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_BROWSER_DATABASE_URL,
    webauthn_rp_id="localhost",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    log_path=DEFAULT_APP_LOG_PATH,
    pid_path=DEFAULT_APP_PID_PATH,
) -> None:
    start_app(
        c,
        seed_path=seed_path,
        database_url=database_url,
        webauthn_rp_id=webauthn_rp_id,
        host=host,
        port=port,
        log_path=log_path,
        pid_path=pid_path,
    )
    try:
        wait_for_app(c, url=f"http://{host}:{port}/health")
        run_browser_e2e(
            c,
            preview_base_url=f"http://localhost:{port}",
            e2e_seed_path=e2e_seed_path,
            webauthn_rp_id=webauthn_rp_id,
        )
    finally:
        stop_app(c, pid_path=pid_path)


@task(pre=[check_python, install_js, check_js, install_browser, check_browser_e2e])
def verify(c) -> None:
    """Run the full local verification flow used before pushing."""
