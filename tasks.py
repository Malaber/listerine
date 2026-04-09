from __future__ import annotations

import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
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
DEFAULT_IOS_E2E_PORT = 8017
DEFAULT_IOS_E2E_BASE_URL = f"http://localhost:{DEFAULT_IOS_E2E_PORT}"
DEFAULT_IOS_E2E_DATABASE_URL = "sqlite+aiosqlite:///./tmp-ios-e2e.db"
DEFAULT_IOS_E2E_LOG_PATH = "ios-e2e-server.log"
DEFAULT_IOS_E2E_PID_PATH = "ios-e2e-server.pid"
DEFAULT_IOS_E2E_USER_EMAIL = "listerine@schaedler.rocks"
DEFAULT_IOS_UI_E2E_PORT = 8018
DEFAULT_IOS_UI_E2E_BASE_URL = f"http://127.0.0.1:{DEFAULT_IOS_UI_E2E_PORT}"
DEFAULT_IOS_UI_E2E_DATABASE_URL = "sqlite+aiosqlite:///./tmp-ios-ui-e2e.db"
DEFAULT_IOS_UI_E2E_LOG_PATH = "ios-ui-e2e-server.log"
DEFAULT_IOS_UI_E2E_PID_PATH = "ios-ui-e2e-server.pid"
DEFAULT_IOS_UI_E2E_ARTIFACT_DIR = "e2e-artifacts/ios-ui-e2e"
DEFAULT_IOS_UI_E2E_RESULT_BUNDLE = "ListerineUITests.xcresult"
DEFAULT_IOS_UI_E2E_DEVICE = "iPhone 17"
DEFAULT_IOS_UI_E2E_INITIAL_LIST = "Browser Test Shop"
DEFAULT_IOS_SIMULATOR_DESTINATION = "generic/platform=iOS Simulator"
DEFAULT_IOS_APP_BACKEND_URL = "https://listerine.malaber.de"
DEFAULT_IOS_APP_BUNDLE_IDENTIFIER = "de.malaber.listerine"
DEFAULT_IOS_APP_DEVELOPMENT_TEAM = "VWKG94374J"
IOS_PROJECT_YML_PATH = ROOT / "ios" / "ListerineIOS" / "project.yml"
IOS_ENTITLEMENTS_PATH = ROOT / "ios" / "ListerineIOS" / "App" / "Listerine.entitlements"
IOS_GENERATED_CONFIG_PATH = (
    ROOT / "ios" / "ListerineIOS" / "App" / "BuildConfiguration.generated.swift"
)
STABLE_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _tool_path(name: str) -> str:
    current_bin = Path(sys.executable).resolve().parent / name
    if current_bin.exists():
        return str(current_bin)

    local_bin = ROOT / ".venv" / "bin" / name
    if local_bin.exists():
        return str(local_bin)

    return name


def _git_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


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


def _print_hidden_output(result) -> None:
    for stream_name in ("stdout", "stderr"):
        output = getattr(result, stream_name, "") or ""
        if output:
            print(output, end="" if output.endswith("\n") else "\n")


def _run_quiet(c, command: str, **kwargs):
    result = c.run(command, hide=True, warn=True, **kwargs)
    if result.exited != 0:
        _print_hidden_output(result)
        raise Exit(f"Command failed with exit code {result.exited}: {command}")
    return result


def _node_bootstrap() -> str:
    version_check = (
        "node -e \"process.exit(Number(process.versions.node.split('.')[0]) === 24 ? 0 : 1)\""
    )
    return (
        f"if {version_check}; then true; "
        'elif [ -s "$HOME/.nvm/nvm.sh" ]; then '
        'source "$HOME/.nvm/nvm.sh" && nvm use 24 >/dev/null; '
        "else "
        "echo 'Node 24.x is required. Run `nvm use 24` or equivalent first.' >&2; "
        "exit 1; "
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
    ui_test_bootstrap_enabled: bool = False,
) -> dict[str, str]:
    return _python_env(
        SEED_DATA_PATH=seed_path,
        DATABASE_URL=database_url,
        WEBAUTHN_RP_ID=webauthn_rp_id,
        UI_TEST_BOOTSTRAP_ENABLED="true" if ui_test_bootstrap_enabled else "false",
    )


def _ios_ui_test_env(
    *,
    base_url: str,
    user_email: str,
    artifact_dir: str,
    initial_list_name: str,
) -> dict[str, str]:
    env = _ios_toolchain_env()
    env.update(
        {
            "LISTERINE_UI_TEST_BASE_URL": base_url,
            "LISTERINE_UI_TEST_USER_EMAIL": user_email,
            "LISTERINE_UI_TEST_ARTIFACT_DIR": str((ROOT / artifact_dir).resolve()),
            "LISTERINE_UI_TEST_INITIAL_LIST_NAME": initial_list_name,
        }
    )
    return env


def _write_ios_ui_e2e_summary(artifact_dir: str) -> None:
    artifact_path = ROOT / artifact_dir
    screenshots = sorted(path.name for path in artifact_path.glob("*.png"))
    result_bundle_path = artifact_path / DEFAULT_IOS_UI_E2E_RESULT_BUNDLE
    summary_lines = [
        "# iOS UI e2e",
        "",
        f"Stored screenshots: {len(screenshots)}",
    ]
    if screenshots:
        summary_lines.extend(["", "## Screenshots"])
        summary_lines.extend(f"- {name}" for name in screenshots)
    if result_bundle_path.exists():
        summary_lines.extend(
            [
                "",
                "## Result Bundle",
                f"- {DEFAULT_IOS_UI_E2E_RESULT_BUNDLE}",
                "- XCTest screenshot attachments are preserved inside this bundle for CI download.",
            ]
        )
    (artifact_path / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


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


def _wait_for_pid_exit(pid: int, timeout_seconds: float = 10.0, sleep_seconds: float = 0.1) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            waited_pid, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            waited_pid = 0
        if waited_pid == pid:
            return
        if not _pid_is_running(pid):
            return
        time.sleep(sleep_seconds)
    raise Exit(f"Timed out waiting for pid {pid} to exit")


def _database_url_for_device(database_url: str, device: str) -> str:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return database_url
    database_path = database_url.removeprefix(prefix)
    root, extension = os.path.splitext(database_path)
    suffix = extension or ".db"
    return f"{prefix}{root}-{device}{suffix}"


def _reset_sqlite_database_file(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    database_path = Path(database_url.removeprefix(prefix))
    for extra_suffix in ("", "-shm", "-wal"):
        database_path.with_name(f"{database_path.name}{extra_suffix}").unlink(missing_ok=True)


def _run_browser_e2e_for_device(
    c,
    *,
    device: str,
    base_url: str,
    seed_path: str,
    database_url: str,
    webauthn_rp_id: str,
    host: str,
    port: int,
    artifact_root: str,
    log_path: str,
    pid_path: str,
) -> None:
    device_database_url = _database_url_for_device(database_url, device)
    _reset_sqlite_database_file(device_database_url)
    start_app(
        c,
        seed_path=seed_path,
        database_url=device_database_url,
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
            preview_base_url=base_url,
            e2e_seed_path=seed_path,
            webauthn_rp_id=webauthn_rp_id,
            artifact_dir=f"{artifact_root}/ui-e2e-{device}",
            device=device,
        )
    finally:
        stop_app(c, pid_path=pid_path)


def _ios_e2e_env(
    *,
    base_url: str,
    e2e_seed_path: str,
    webauthn_rp_id: str,
    user_email: str,
    origin: str = "",
) -> dict[str, str]:
    package_dir = ROOT / "ios" / "ListerineIOS"
    clang_module_cache = package_dir / ".clang-module-cache"
    clang_module_cache.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "LISTERINE_E2E_BASE_URL": base_url,
            "LISTERINE_E2E_SEED_PATH": (
                str((ROOT / e2e_seed_path).resolve())
                if not os.path.isabs(e2e_seed_path)
                else e2e_seed_path
            ),
            "LISTERINE_E2E_USER_EMAIL": user_email,
            "LISTERINE_E2E_RP_ID": webauthn_rp_id,
            "LISTERINE_E2E_ORIGIN": origin.strip(),
            "DEVELOPER_DIR": env.get("DEVELOPER_DIR", "/Applications/Xcode.app/Contents/Developer"),
            "CLANG_MODULE_CACHE_PATH": env.get(
                "CLANG_MODULE_CACHE_PATH", str(clang_module_cache.resolve())
            ),
        }
    )
    return env


def _ios_toolchain_env() -> dict[str, str]:
    package_dir = ROOT / "ios" / "ListerineIOS"
    clang_module_cache = package_dir / ".clang-module-cache"
    clang_module_cache.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "DEVELOPER_DIR": env.get("DEVELOPER_DIR", "/Applications/Xcode.app/Contents/Developer"),
            "CLANG_MODULE_CACHE_PATH": env.get(
                "CLANG_MODULE_CACHE_PATH", str(clang_module_cache.resolve())
            ),
        }
    )
    return env


def _validated_ios_backend_host(backend_url: str) -> str:
    parsed = urlparse(backend_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise Exit("configure-ios-app requires a valid http or https backend_url.")
    return parsed.hostname


def _replace_project_setting(contents: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^(\s*{re.escape(key)}:\s*).*$", re.MULTILINE)
    replacement = rf"\1{value}"
    if pattern.search(contents):
        return pattern.sub(replacement, contents, count=1)
    raise Exit(f"Could not find {key} in {IOS_PROJECT_YML_PATH}.")


def _write_ios_entitlements(host: str) -> None:
    # Native Apple passkeys only work when the signed app declares the same
    # webcredentials host that the backend advertises in its AASA file.
    IOS_ENTITLEMENTS_PATH.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                '<plist version="1.0">',
                "<dict>",
                "\t<key>com.apple.developer.associated-domains</key>",
                "\t<array>",
                f"\t\t<string>webcredentials:{host}</string>",
                "\t</array>",
                "</dict>",
                "</plist>",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_ios_generated_config(backend_url: str) -> None:
    IOS_GENERATED_CONFIG_PATH.write_text(
        "\n".join(
            [
                "import Foundation",
                "",
                "enum GeneratedBuildConfiguration {",
                f'    static let backendURL = "{backend_url}"',
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _latest_stable_version_from_tags(tags: list[str]) -> str:
    versions = [
        tuple(map(int, match.groups()))
        for tag in tags
        if (match := STABLE_TAG_PATTERN.fullmatch(tag))
    ]
    if not versions:
        return "0.1.0"
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch}"


def _next_stable_version(version: str, tags: list[str]) -> str:
    major, minor, patch = map(int, version.split("."))
    existing_tags = set(tags)
    while True:
        patch += 1
        candidate = f"{major}.{minor}.{patch}"
        if f"v{candidate}" not in existing_tags:
            return candidate


def _next_rc_version(version: str, run_number: int, tags: list[str]) -> str:
    rc_number = run_number
    existing_tags = set(tags)
    while True:
        candidate = f"{version}-rc.{rc_number}"
        if f"v{candidate}" not in existing_tags:
            return candidate
        rc_number += 1


def _compute_version_values(ref_name: str, run_number: int, tags: list[str]) -> dict[str, str]:
    base_version = _next_stable_version(_latest_stable_version_from_tags(tags), tags)
    if ref_name == "main":
        release_version = base_version
    else:
        release_version = _next_rc_version(base_version, run_number, tags)
    return {
        "base_version": base_version,
        "release_version": release_version,
        "git_tag": f"v{release_version}",
    }


def _write_github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as fh:
            for key, value in values.items():
                fh.write(f"{key}={value}\n")
        return

    for key, value in values.items():
        print(f"{key}={value}")


@task
def setup(c) -> None:
    c.run("./.codex/setup.sh", pty=False, shell="/bin/bash")


@task(pre=[setup])
def bootstrap_ci(c) -> None:
    """Install the shared Python tooling CI tasks depend on."""


@task(
    help={
        "ref_name": "Git ref name used to decide stable vs rc versioning.",
        "run_number": "Run number used to derive rc suffixes on non-main refs.",
    }
)
def compute_version(c, ref_name="", run_number="") -> None:
    resolved_ref_name = ref_name or os.environ.get("REF_NAME") or os.environ.get("GITHUB_REF_NAME")
    resolved_run_number = (
        str(run_number)
        if run_number
        else (os.environ.get("RUN_NUMBER") or os.environ.get("GITHUB_RUN_NUMBER"))
    )
    if not resolved_ref_name:
        raise Exit("compute-version requires ref_name or REF_NAME/GITHUB_REF_NAME.")
    if not resolved_run_number:
        raise Exit("compute-version requires run_number or RUN_NUMBER/GITHUB_RUN_NUMBER.")

    tags = _git_lines("tag", "--list", "v*")
    values = _compute_version_values(
        ref_name=resolved_ref_name,
        run_number=int(resolved_run_number),
        tags=tags,
    )
    _write_github_output(values)


@task(help={"python_bin": "Python executable to use when creating the repo virtualenv."})
def setup_venv(c, python_bin="python3.14") -> None:
    venv_dir = ROOT / ".venv"
    if not venv_dir.exists():
        _run_quiet(c, f"{shlex.quote(python_bin)} -m venv .venv", pty=False, shell="/bin/bash")

    pip_path = ROOT / ".venv" / "bin" / "pip"
    _run_quiet(
        c,
        f"{shlex.quote(str(pip_path))} install -e '.[dev]'",
        env=_pip_env(),
        pty=False,
        shell="/bin/bash",
    )


@task(
    help={
        "python_bin": "Python executable to use when creating the repo virtualenv.",
        "with_browser": "Also install Playwright's Chromium browser bundle.",
        "browser_with_deps": "Use Playwright's --with-deps flow when installing the browser.",
    }
)
def install_deps(c, python_bin="python3.14", with_browser=False, browser_with_deps=False) -> None:
    setup_venv.body(c, python_bin=python_bin)
    install_js.body(c)
    if with_browser:
        install_browser.body(c, with_deps=browser_with_deps)


@task
def black_check(c) -> None:
    c.run(_black_command("--check", "."), env=_python_env(), pty=False)


@task
def flake8_check(c) -> None:
    c.run(f"{shlex.quote(_tool_path('flake8'))} .", env=_python_env(), pty=False)


@task
def test_python(c) -> None:
    c.run(f"{shlex.quote(_tool_path('pytest'))} -q", env=_python_env(), pty=False)


@task
def format_python(c) -> None:
    c.run(_black_command("."), env=_python_env(), pty=False)


@task(pre=[black_check, flake8_check])
def lint_python(c) -> None:
    """Run the Python formatter and linter checks."""


@task(pre=[lint_python, test_python])
def check_python(c) -> None:
    """Run the Python lint and test checks."""


@task
def install_js(c) -> None:
    _run_quiet(c, _node_command("npm ci"), pty=False, shell="/bin/bash")


@task
def check_js(c) -> None:
    c.run(_node_command("npm run --silent test:js"), pty=False, shell="/bin/bash")


@task(help={"with_deps": "Use Playwright's system dependency install flow."})
def install_browser(c, with_deps=False) -> None:
    playwright_install = "npx playwright install chromium"
    if with_deps:
        playwright_install = "npx playwright install --with-deps chromium"

    _run_quiet(c, _node_command(playwright_install), pty=False, shell="/bin/bash")


@task(help={"database_url": "SQLite database URL used by the browser e2e flow."})
def clean_browser_e2e(c, database_url=DEFAULT_BROWSER_DATABASE_URL) -> None:
    """Remove the generated browser e2e SQLite database and sidecar files."""
    _reset_sqlite_database_file(database_url)


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
    ui_test_bootstrap_enabled=False,
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
        ui_test_bootstrap_enabled=str(ui_test_bootstrap_enabled).lower() in {"1", "true", "yes"},
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
    else:
        try:
            _wait_for_pid_exit(pid)
        except Exit:
            os.kill(pid, signal.SIGKILL)
            _wait_for_pid_exit(pid, timeout_seconds=5.0)
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
        "artifact_dir": "Artifact directory used by the Playwright flow.",
        "device": "Playwright device name for the browser flow.",
    }
)
def run_browser_e2e(
    c,
    preview_base_url=DEFAULT_PREVIEW_BASE_URL,
    e2e_seed_path=DEFAULT_BROWSER_SEED_PATH,
    webauthn_rp_id="localhost",
    artifact_dir="e2e-artifacts/ui-e2e-desktop",
    device="desktop",
) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PREVIEW_BASE_URL": preview_base_url,
            "E2E_SEED_PATH": e2e_seed_path,
            "WEBAUTHN_RP_ID": webauthn_rp_id,
            "PREVIEW_ARTIFACT_DIR": artifact_dir,
        }
    )
    if device != "desktop":
        env["E2E_DEVICE"] = device
    c.run(_node_command("node scripts/run_ui_e2e.mjs"), env=env, pty=False, shell="/bin/bash")


@task(
    help={
        "package_path": "Swift package path for the reusable iOS core.",
    }
)
def check_ios_package(c, package_path="ios/ListerineIOS") -> None:
    env = _ios_toolchain_env()
    c.run(
        f"xcrun swift test --package-path {shlex.quote(package_path)} --enable-code-coverage",
        env=env,
        pty=False,
        shell="/bin/bash",
    )


@task
def install_xcodegen(c) -> None:
    c.run(
        "brew list xcodegen >/dev/null 2>&1 || brew install xcodegen",
        pty=False,
        shell="/bin/bash",
    )


@task(
    help={
        "backend_url": (
            "Build-time backend URL embedded into the native app and used for "
            "webcredentials:<host>."
        ),
        "passkey_domain": (
            "Optional Associated Domains host for native passkeys. Defaults to "
            "the backend host, but can be a shared parent domain such as "
            "pr.listerine.malaber.de."
        ),
        "bundle_id": (
            "Bundle identifier used for the native app build; the final Apple "
            "appID is TEAM_ID.bundle_id."
        ),
        "development_team": (
            "Apple Developer team ID to stamp into the generated Xcode project. "
            "Defaults to the repo's current shipping team."
        ),
        "regenerate_project": "Regenerate the Xcode project after updating the config.",
    }
)
def configure_ios_app(
    c,
    backend_url=DEFAULT_IOS_APP_BACKEND_URL,
    passkey_domain="",
    bundle_id=DEFAULT_IOS_APP_BUNDLE_IDENTIFIER,
    development_team=DEFAULT_IOS_APP_DEVELOPMENT_TEAM,
    regenerate_project=True,
) -> None:
    # Keep the embedded backend URL and associated domain aligned so self-hosted
    # builders can stamp one consistent passkey configuration into the app.
    host = _validated_ios_backend_host(backend_url)
    passkey_host = passkey_domain.strip() or host
    project_yml = IOS_PROJECT_YML_PATH.read_text(encoding="utf-8")
    project_yml = _replace_project_setting(
        project_yml,
        "PRODUCT_BUNDLE_IDENTIFIER",
        bundle_id,
    )
    project_yml = _replace_project_setting(
        project_yml,
        "DEVELOPMENT_TEAM",
        development_team,
    )
    project_yml = _replace_project_setting(
        project_yml,
        "INFOPLIST_KEY_ListerineBackendBaseURL",
        backend_url,
    )
    IOS_PROJECT_YML_PATH.write_text(project_yml, encoding="utf-8")
    _write_ios_entitlements(passkey_host)
    _write_ios_generated_config(backend_url)
    if str(regenerate_project).lower() not in {"0", "false", "no"}:
        install_xcodegen.body(c)
        generate_ios_project.body(c)


@task(
    help={
        "project_dir": "Directory that contains the iOS XcodeGen project spec.",
    }
)
def generate_ios_project(c, project_dir="ios/ListerineIOS") -> None:
    c.run(
        f"cd {shlex.quote(project_dir)} && xcodegen generate",
        pty=False,
        shell="/bin/bash",
    )


@task(
    help={
        "project_dir": "Directory that contains the generated iOS Xcode project.",
        "scheme": "Xcode scheme to build.",
        "configuration": "Xcode build configuration to use.",
        "destination": "Xcode destination used for the simulator build.",
    }
)
def build_ios_simulator(
    c,
    project_dir="ios/ListerineIOS",
    scheme="Listerine",
    configuration="Debug",
    destination=DEFAULT_IOS_SIMULATOR_DESTINATION,
) -> None:
    env = _ios_toolchain_env()
    c.run(
        " ".join(
            [
                f"cd {shlex.quote(project_dir)} &&",
                "xcodebuild",
                "-project ListerineApp.xcodeproj",
                f"-scheme {shlex.quote(scheme)}",
                f"-configuration {shlex.quote(configuration)}",
                f"-destination {shlex.quote(destination)}",
                "CODE_SIGNING_ALLOWED=NO",
                "build",
            ]
        ),
        env=env,
        pty=False,
        shell="/bin/bash",
    )


@task(
    help={
        "base_url": "Base URL used by the native iOS backend e2e flow.",
        "e2e_seed_path": "Fixture that contains passkey data for the native iOS flow.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the native iOS flow.",
        "user_email": "Seeded user email used for the native iOS passkey login.",
        "origin": (
            "Optional origin embedded into the seeded passkey assertion. Defaults to "
            "the base_url origin, but can be set to a shared native passkey host such "
            "as https://pr.listerine.malaber.de."
        ),
    }
)
def run_ios_e2e(
    c,
    base_url=DEFAULT_IOS_E2E_BASE_URL,
    e2e_seed_path=DEFAULT_BROWSER_SEED_PATH,
    webauthn_rp_id="localhost",
    user_email=DEFAULT_IOS_E2E_USER_EMAIL,
    origin="",
) -> None:
    env = _ios_e2e_env(
        base_url=base_url,
        e2e_seed_path=e2e_seed_path,
        webauthn_rp_id=webauthn_rp_id,
        user_email=user_email,
        origin=origin,
    )
    c.run(
        "xcrun swift test --package-path ios/ListerineIOS --filter LiveBackendE2ETests",
        env=env,
        pty=False,
        shell="/bin/bash",
    )


@task(
    help={
        "base_url": "Base URL used by the native iOS UI e2e flow.",
        "user_email": "Seeded user email used for bootstrap login into the app.",
        "artifact_dir": "Directory used to store native iOS UI screenshots.",
        "device_name": "Simulator device name used for XCUITest.",
        "initial_list_name": "Seeded list name that should open first inside the app.",
    }
)
def run_ios_ui_e2e(
    c,
    base_url=DEFAULT_IOS_UI_E2E_BASE_URL,
    user_email=DEFAULT_IOS_E2E_USER_EMAIL,
    artifact_dir=DEFAULT_IOS_UI_E2E_ARTIFACT_DIR,
    device_name=DEFAULT_IOS_UI_E2E_DEVICE,
    initial_list_name=DEFAULT_IOS_UI_E2E_INITIAL_LIST,
) -> None:
    artifact_path = ROOT / artifact_dir
    artifact_path.mkdir(parents=True, exist_ok=True)
    for existing_png in artifact_path.glob("*.png"):
        existing_png.unlink()
    result_bundle_path = artifact_path / DEFAULT_IOS_UI_E2E_RESULT_BUNDLE
    shutil.rmtree(result_bundle_path, ignore_errors=True)

    env = _ios_ui_test_env(
        base_url=base_url,
        user_email=user_email,
        artifact_dir=artifact_dir,
        initial_list_name=initial_list_name,
    )
    c.run(
        " ".join(
            [
                "cd ios/ListerineIOS &&",
                "xcodebuild",
                "-project ListerineApp.xcodeproj",
                "-scheme Listerine",
                f"-destination {shlex.quote(f'platform=iOS Simulator,name={device_name}')}",
                f"-resultBundlePath {shlex.quote(str(result_bundle_path.resolve()))}",
                "-only-testing:ListerineUITests",
                "test",
            ]
        ),
        env=env,
        pty=False,
        shell="/bin/bash",
    )
    _write_ios_ui_e2e_summary(artifact_dir)


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
    _reset_sqlite_database_file(database_url)
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


@task(
    help={
        "backend_url": (
            "Backend URL whose hostname should be used as the WebAuthn RP ID; "
            "the deployed backend must also serve an AASA file for the signed "
            "appID on that host."
        ),
        "seed_path": "Fixture used to seed the local app database.",
        "database_url": "Database URL for the temporary local app.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def start_ios_backend(
    c,
    backend_url=DEFAULT_IOS_APP_BACKEND_URL,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_IOS_E2E_DATABASE_URL,
    host=DEFAULT_HOST,
    port=DEFAULT_IOS_E2E_PORT,
    log_path=DEFAULT_IOS_E2E_LOG_PATH,
    pid_path=DEFAULT_IOS_E2E_PID_PATH,
) -> None:
    start_app(
        c,
        seed_path=seed_path,
        database_url=database_url,
        webauthn_rp_id=_validated_ios_backend_host(backend_url),
        host=host,
        port=port,
        log_path=log_path,
        pid_path=pid_path,
    )


@task(
    help={
        "seed_path": "Fixture used to seed the local app database.",
        "e2e_seed_path": "Fixture that contains passkey data for the native iOS flow.",
        "database_url": "Database URL for the temporary local app.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the native iOS flow.",
        "user_email": "Seeded user email used for the native iOS passkey login.",
        "origin": (
            "Optional origin embedded into the seeded passkey assertion. Defaults to "
            "http://localhost:<port>, but can be overridden to model shared native "
            "passkey hosts."
        ),
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def check_ios_e2e(
    c,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    e2e_seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_IOS_E2E_DATABASE_URL,
    webauthn_rp_id="localhost",
    user_email=DEFAULT_IOS_E2E_USER_EMAIL,
    origin="",
    host=DEFAULT_HOST,
    port=DEFAULT_IOS_E2E_PORT,
    log_path=DEFAULT_IOS_E2E_LOG_PATH,
    pid_path=DEFAULT_IOS_E2E_PID_PATH,
) -> None:
    _reset_sqlite_database_file(database_url)
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
        run_ios_e2e(
            c,
            base_url=f"http://127.0.0.1:{port}",
            e2e_seed_path=e2e_seed_path,
            webauthn_rp_id=webauthn_rp_id,
            user_email=user_email,
            origin=origin,
        )
    finally:
        stop_app(c, pid_path=pid_path)


@task(
    help={
        "seed_path": "Fixture used to seed the local app database.",
        "database_url": "Database URL for the temporary local app.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the native app.",
        "user_email": "Seeded user email used for UI bootstrap login.",
        "artifact_dir": "Directory used to store native iOS UI screenshots.",
        "device_name": "Simulator device name used for XCUITest.",
        "initial_list_name": "Seeded list name that should open first inside the app.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def check_ios_ui_e2e(
    c,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_IOS_UI_E2E_DATABASE_URL,
    webauthn_rp_id="localhost",
    user_email=DEFAULT_IOS_E2E_USER_EMAIL,
    artifact_dir=DEFAULT_IOS_UI_E2E_ARTIFACT_DIR,
    device_name=DEFAULT_IOS_UI_E2E_DEVICE,
    initial_list_name=DEFAULT_IOS_UI_E2E_INITIAL_LIST,
    host=DEFAULT_HOST,
    port=DEFAULT_IOS_UI_E2E_PORT,
    log_path=DEFAULT_IOS_UI_E2E_LOG_PATH,
    pid_path=DEFAULT_IOS_UI_E2E_PID_PATH,
) -> None:
    _reset_sqlite_database_file(database_url)
    start_app(
        c,
        seed_path=seed_path,
        database_url=database_url,
        webauthn_rp_id=webauthn_rp_id,
        host=host,
        port=port,
        log_path=log_path,
        pid_path=pid_path,
        ui_test_bootstrap_enabled=True,
    )
    try:
        wait_for_app(c, url=f"http://{host}:{port}/health")
        generate_ios_project.body(c)
        run_ios_ui_e2e(
            c,
            base_url=f"http://127.0.0.1:{port}",
            user_email=user_email,
            artifact_dir=artifact_dir,
            device_name=device_name,
            initial_list_name=initial_list_name,
        )
    finally:
        stop_app(c, pid_path=pid_path)


@task(
    pre=[
        install_xcodegen,
        check_ios_package,
        check_ios_e2e,
        generate_ios_project,
        build_ios_simulator,
        check_ios_ui_e2e,
    ]
)
def check_ios_ci(c) -> None:
    """Run the full native iOS CI flow.

    This includes package checks, live backend e2e, simulator UI e2e,
    project generation, and simulator build.
    """


@task(
    help={
        "base_url": "Browser-facing base URL used by the Playwright flow.",
        "seed_path": "Fixture used to seed the local app database and browser flow.",
        "database_url": "Base database URL used to derive per-device SQLite files.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the browser.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "artifact_root": "Directory used to store per-device browser artifacts.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def browser_e2e(
    c,
    base_url=DEFAULT_PREVIEW_BASE_URL,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_BROWSER_DATABASE_URL,
    webauthn_rp_id="localhost",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    artifact_root="e2e-artifacts",
    log_path=DEFAULT_APP_LOG_PATH,
    pid_path=DEFAULT_APP_PID_PATH,
) -> None:
    """Run seeded browser e2e for desktop and iPhone and store artifacts per device."""
    for device in ("desktop", "iphone"):
        _run_browser_e2e_for_device(
            c,
            device=device,
            base_url=base_url,
            seed_path=seed_path,
            database_url=database_url,
            webauthn_rp_id=webauthn_rp_id,
            host=host,
            port=port,
            artifact_root=artifact_root,
            log_path=log_path,
            pid_path=pid_path,
        )


@task(
    help={
        "base_url": "Browser-facing base URL used by the Playwright flow.",
        "seed_path": "Fixture used to seed the local app database and browser flow.",
        "database_url": "Base database URL used to derive the desktop SQLite file.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the browser.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "artifact_root": "Directory used to store browser artifacts.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def browser_e2e_desktop(
    c,
    base_url=DEFAULT_PREVIEW_BASE_URL,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_BROWSER_DATABASE_URL,
    webauthn_rp_id="localhost",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    artifact_root="e2e-artifacts",
    log_path=DEFAULT_APP_LOG_PATH,
    pid_path=DEFAULT_APP_PID_PATH,
) -> None:
    """Run seeded browser e2e for desktop only."""
    _run_browser_e2e_for_device(
        c,
        device="desktop",
        base_url=base_url,
        seed_path=seed_path,
        database_url=database_url,
        webauthn_rp_id=webauthn_rp_id,
        host=host,
        port=port,
        artifact_root=artifact_root,
        log_path=log_path,
        pid_path=pid_path,
    )


@task(
    help={
        "base_url": "Browser-facing base URL used by the Playwright flow.",
        "seed_path": "Fixture used to seed the local app database and browser flow.",
        "database_url": "Base database URL used to derive the iPhone SQLite file.",
        "webauthn_rp_id": "WebAuthn relying party ID exposed to the browser.",
        "host": "Host to bind the local app server to.",
        "port": "Port to bind the local app server to.",
        "artifact_root": "Directory used to store browser artifacts.",
        "log_path": "File used for uvicorn logs.",
        "pid_path": "File used to store the started server PID.",
    }
)
def browser_e2e_mobile(
    c,
    base_url=DEFAULT_PREVIEW_BASE_URL,
    seed_path=DEFAULT_BROWSER_SEED_PATH,
    database_url=DEFAULT_BROWSER_DATABASE_URL,
    webauthn_rp_id="localhost",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
    artifact_root="e2e-artifacts",
    log_path=DEFAULT_APP_LOG_PATH,
    pid_path=DEFAULT_APP_PID_PATH,
) -> None:
    """Run seeded browser e2e for iPhone only."""
    _run_browser_e2e_for_device(
        c,
        device="iphone",
        base_url=base_url,
        seed_path=seed_path,
        database_url=database_url,
        webauthn_rp_id=webauthn_rp_id,
        host=host,
        port=port,
        artifact_root=artifact_root,
        log_path=log_path,
        pid_path=pid_path,
    )


@task(pre=[check_python, install_js, check_js, install_browser, check_browser_e2e])
def verify(c) -> None:
    """Run the full local verification flow used before pushing."""
