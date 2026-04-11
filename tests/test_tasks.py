import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

TASKS_PATH = Path(__file__).resolve().parents[1] / "tasks.py"
TASKS_SPEC = importlib.util.spec_from_file_location("tasks", TASKS_PATH)
assert TASKS_SPEC is not None
assert TASKS_SPEC.loader is not None
tasks = importlib.util.module_from_spec(TASKS_SPEC)
TASKS_SPEC.loader.exec_module(tasks)


class RunResult:
    def __init__(self, exited: int, stdout: str = "", stderr: str = "") -> None:
        self.exited = exited
        self.stdout = stdout
        self.stderr = stderr


def test_database_url_for_device_uses_distinct_sqlite_file() -> None:
    database_url = "sqlite+aiosqlite:///./tmp-ci-ui-e2e.db"

    assert tasks._database_url_for_device(database_url, "iphone") == (
        "sqlite+aiosqlite:///./tmp-ci-ui-e2e-iphone.db"
    )


def test_database_url_for_device_leaves_non_sqlite_urls_unchanged() -> None:
    database_url = "postgresql+asyncpg://user:password@example.com/planini"

    assert tasks._database_url_for_device(database_url, "iphone") == database_url


def test_reset_sqlite_database_file_removes_database_and_sidecars(tmp_path: Path) -> None:
    database_path = tmp_path / "browser-e2e.db"
    for suffix in ("", "-shm", "-wal"):
        database_path.with_name(f"{database_path.name}{suffix}").write_text(
            "data", encoding="utf-8"
        )

    tasks._reset_sqlite_database_file(f"sqlite+aiosqlite:///{database_path}")

    for suffix in ("", "-shm", "-wal"):
        assert not database_path.with_name(f"{database_path.name}{suffix}").exists()


def test_clean_browser_e2e_removes_database_and_sidecars(tmp_path: Path) -> None:
    database_path = tmp_path / "browser-e2e.db"
    for suffix in ("", "-shm", "-wal"):
        database_path.with_name(f"{database_path.name}{suffix}").write_text(
            "data", encoding="utf-8"
        )

    tasks.clean_browser_e2e.body(None, database_url=f"sqlite+aiosqlite:///{database_path}")

    for suffix in ("", "-shm", "-wal"):
        assert not database_path.with_name(f"{database_path.name}{suffix}").exists()


def test_wait_for_pid_exit_returns_once_process_is_gone(monkeypatch) -> None:
    states = iter([True, True, False])
    monkeypatch.setattr(tasks.os, "waitpid", lambda pid, flags: (0, 0))
    monkeypatch.setattr(tasks, "_pid_is_running", lambda pid: next(states))
    monkeypatch.setattr(tasks.time, "sleep", lambda _: None)

    tasks._wait_for_pid_exit(123)


def test_wait_for_pid_exit_reaps_child_process(monkeypatch) -> None:
    monkeypatch.setattr(tasks.os, "waitpid", lambda pid, flags: (pid, 0))

    tasks._wait_for_pid_exit(123)


def test_ios_ui_e2e_failure_summaries_returns_empty_without_database(tmp_path: Path) -> None:
    assert tasks._ios_ui_e2e_failure_summaries(tmp_path / "missing.xcresult") == []


def test_ios_ui_e2e_failure_summaries_reads_failed_test_messages(tmp_path: Path) -> None:
    bundle_path = tmp_path / "PlaniniUITests.xcresult"
    bundle_path.mkdir()
    database_path = bundle_path / "database.sqlite3"

    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE TestCases (name TEXT);
            CREATE TABLE TestCaseRuns (testCase_fk INTEGER, result TEXT);
            CREATE TABLE TestIssues (
                testCaseRun_fk INTEGER,
                compactDescription TEXT,
                detailedDescription TEXT,
                orderInOwner INTEGER
            );
            INSERT INTO TestCases(rowid, name) VALUES (1, 'testListViewFlow()');
            INSERT INTO TestCaseRuns(rowid, testCase_fk, result) VALUES (1, 1, 'Failure');
            INSERT INTO TestIssues(
                testCaseRun_fk,
                compactDescription,
                detailedDescription,
                orderInOwner
            ) VALUES (1, 'Compact failure', 'Detailed failure', 0);
            """
        )

    assert tasks._ios_ui_e2e_failure_summaries(bundle_path) == [
        "testListViewFlow() [Failure]: Detailed failure"
    ]


def test_stop_app_waits_for_exit_before_removing_pid_file(tmp_path: Path, monkeypatch) -> None:
    pid_path = tmp_path / "ui-e2e-server.pid"
    pid_path.write_text("4321\n", encoding="utf-8")
    waits: list[tuple[int, float]] = []
    signals: list[tuple[int, int]] = []

    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    monkeypatch.setattr(tasks, "_read_pid", lambda path: 4321)
    monkeypatch.setattr(
        tasks,
        "_wait_for_pid_exit",
        lambda pid, timeout_seconds=10.0: waits.append((pid, timeout_seconds)),
    )
    monkeypatch.setattr(tasks.os, "kill", lambda pid, sig: signals.append((pid, sig)))

    tasks.stop_app.body(None, pid_path=pid_path.name)

    assert signals == [(4321, tasks.signal.SIGTERM)]
    assert waits == [(4321, 10.0)]
    assert not pid_path.exists()


def test_pid_is_running_reports_missing_process():
    assert tasks._pid_is_running(999999) is False


def test_latest_stable_version_from_tags_defaults_when_no_stable_tags():
    assert tasks._latest_stable_version_from_tags(["v1.2.3-rc.1", "notes"]) == "0.1.0"


def test_compute_version_values_for_main_uses_next_stable_tag():
    values = tasks._compute_version_values(
        ref_name="main",
        run_number=42,
        tags=["v1.2.3", "v1.2.4-rc.1"],
    )

    assert values == {
        "base_version": "1.2.4",
        "release_version": "1.2.4",
        "git_tag": "v1.2.4",
    }


def test_compute_version_values_for_branch_skips_existing_rc_tags():
    values = tasks._compute_version_values(
        ref_name="codex/workflows",
        run_number=7,
        tags=["v1.2.3", "v1.2.4-rc.7", "v1.2.4-rc.8"],
    )

    assert values == {
        "base_version": "1.2.4",
        "release_version": "1.2.4-rc.9",
        "git_tag": "v1.2.4-rc.9",
    }


def test_run_quiet_hides_successful_output() -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0, stdout="noise\n", stderr="more noise\n")

    result = tasks._run_quiet(Context(), "npm ci", pty=False)

    assert result.exited == 0
    assert calls == [("npm ci", {"pty": False, "hide": True, "warn": True})]


def test_run_quiet_prints_captured_output_on_failure(capsys) -> None:
    class Context:
        def run(self, command, **kwargs):
            return RunResult(exited=1, stdout="stdout noise\n", stderr="stderr noise")

    try:
        tasks._run_quiet(Context(), "npm ci")
    except tasks.Exit as exc:
        assert "Command failed with exit code 1: npm ci" in str(exc)
    else:
        raise AssertionError("expected quiet run failure")

    assert capsys.readouterr().out == "stdout noise\nstderr noise\n"


def test_run_browser_e2e_for_device_uses_derived_database_and_artifact_paths(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        tasks,
        "_reset_sqlite_database_file",
        lambda database_url: calls.append(("reset", {"database_url": database_url})),
    )
    monkeypatch.setattr(tasks, "start_app", lambda c, **kwargs: calls.append(("start", kwargs)))
    monkeypatch.setattr(tasks, "wait_for_app", lambda c, **kwargs: calls.append(("wait", kwargs)))
    monkeypatch.setattr(tasks, "run_browser_e2e", lambda c, **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(tasks, "stop_app", lambda c, **kwargs: calls.append(("stop", kwargs)))

    tasks._run_browser_e2e_for_device(
        None,
        device="iphone",
        base_url="http://localhost:8000",
        seed_path="app/fixtures/review_seed_e2e.json",
        database_url="sqlite+aiosqlite:///./tmp-ui-e2e.db",
        webauthn_rp_id="localhost",
        host="127.0.0.1",
        port=8000,
        artifact_root="e2e-artifacts",
        log_path="ui-e2e-server.log",
        pid_path="ui-e2e-server.pid",
    )

    assert calls == [
        ("reset", {"database_url": "sqlite+aiosqlite:///./tmp-ui-e2e-iphone.db"}),
        (
            "start",
            {
                "seed_path": "app/fixtures/review_seed_e2e.json",
                "database_url": "sqlite+aiosqlite:///./tmp-ui-e2e-iphone.db",
                "webauthn_rp_id": "localhost",
                "host": "127.0.0.1",
                "port": 8000,
                "log_path": "ui-e2e-server.log",
                "pid_path": "ui-e2e-server.pid",
            },
        ),
        ("wait", {"url": "http://127.0.0.1:8000/health"}),
        (
            "run",
            {
                "preview_base_url": "http://localhost:8000",
                "e2e_seed_path": "app/fixtures/review_seed_e2e.json",
                "webauthn_rp_id": "localhost",
                "artifact_dir": "e2e-artifacts/ui-e2e-iphone",
                "device": "iphone",
            },
        ),
        ("stop", {"pid_path": "ui-e2e-server.pid"}),
    ]


def test_ios_e2e_env_uses_absolute_seed_and_workspace_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "ROOT", tmp_path)

    env = tasks._ios_e2e_env(
        base_url="http://localhost:8017",
        e2e_seed_path="app/fixtures/review_seed_e2e.json",
        webauthn_rp_id="localhost",
        user_email="ios@example.com",
        origin="https://passkeys.example.com",
    )

    assert env["PLANINI_E2E_BASE_URL"] == "http://localhost:8017"
    assert env["PLANINI_E2E_SEED_PATH"] == str(
        (tmp_path / "app" / "fixtures" / "review_seed_e2e.json").resolve()
    )
    assert env["PLANINI_E2E_USER_EMAIL"] == "ios@example.com"
    assert env["PLANINI_E2E_RP_ID"] == "localhost"
    assert env["PLANINI_E2E_ORIGIN"] == "https://passkeys.example.com"
    assert env["DEVELOPER_DIR"] == "/Applications/Xcode.app/Contents/Developer"
    assert env["CLANG_MODULE_CACHE_PATH"] == str(
        (tmp_path / "ios" / "PlaniniIOS" / ".clang-module-cache").resolve()
    )


def test_ios_toolchain_env_uses_workspace_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "ROOT", tmp_path)

    env = tasks._ios_toolchain_env()

    assert env["DEVELOPER_DIR"] == "/Applications/Xcode.app/Contents/Developer"
    assert env["CLANG_MODULE_CACHE_PATH"] == str(
        (tmp_path / "ios" / "PlaniniIOS" / ".clang-module-cache").resolve()
    )


def test_ios_ui_test_env_uses_absolute_artifact_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    monkeypatch.setattr(
        tasks,
        "_ios_toolchain_env",
        lambda: {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
    )

    env = tasks._ios_ui_test_env(
        base_url="http://localhost:8018",
        bootstrap_base_url="http://127.0.0.1:8018",
        user_email="ios@example.com",
        artifact_dir="e2e-artifacts/ios-ui-e2e",
        initial_list_name="Browser Test Shop",
    )

    assert env["PLANINI_UI_TEST_BASE_URL"] == "http://localhost:8018"
    assert env["PLANINI_UI_TEST_BOOTSTRAP_BASE_URL"] == "http://127.0.0.1:8018"
    assert env["PLANINI_UI_TEST_USER_EMAIL"] == "ios@example.com"
    assert env["PLANINI_UI_TEST_INITIAL_LIST_NAME"] == "Browser Test Shop"
    assert env["PLANINI_UI_TEST_ARTIFACT_DIR"] == str(
        (tmp_path / "e2e-artifacts" / "ios-ui-e2e").resolve()
    )


def test_ios_ui_test_env_includes_injected_session_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    monkeypatch.setattr(
        tasks,
        "_ios_toolchain_env",
        lambda: {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
    )

    env = tasks._ios_ui_test_env(
        base_url="http://localhost:8018",
        bootstrap_base_url="http://127.0.0.1:8018",
        user_email="ios@example.com",
        artifact_dir="e2e-artifacts/ios-ui-e2e",
        initial_list_name="Browser Test Shop",
        access_token="test-token",
        display_name="Test User",
    )

    assert env["PLANINI_UI_TEST_ACCESS_TOKEN"] == "test-token"
    assert env["PLANINI_UI_TEST_DISPLAY_NAME"] == "Test User"


def test_bootstrap_ios_ui_test_session_returns_access_token(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"access_token":"token-123","display_name":"Test User"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(tasks, "urlopen", fake_urlopen)

    session = tasks._bootstrap_ios_ui_test_session(
        base_url="http://localhost:8018",
        user_email="ios@example.com",
    )

    assert session == {"access_token": "token-123", "display_name": "Test User"}
    assert captured == {
        "url": "http://localhost:8018/api/v1/auth/ui-test-bootstrap",
        "method": "POST",
        "body": '{"email": "ios@example.com"}',
        "timeout": 10,
    }


def test_bootstrap_ios_ui_test_session_rejects_incomplete_payload(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"display_name":"Test User"}'

    monkeypatch.setattr(tasks, "urlopen", lambda request, timeout: Response())

    try:
        tasks._bootstrap_ios_ui_test_session(
            base_url="http://localhost:8018",
            user_email="ios@example.com",
        )
    except tasks.Exit as exc:
        assert "incomplete payload" in str(exc)
    else:
        raise AssertionError("expected incomplete iOS UI bootstrap payload to fail")


def test_validated_ios_backend_host_rejects_invalid_urls() -> None:
    try:
        tasks._validated_ios_backend_host("notaurl")
    except tasks.Exit as exc:
        assert "configure-ios-app requires a valid http or https backend_url." in str(exc)
    else:
        raise AssertionError("expected invalid backend URL to fail")


def test_write_ios_entitlements_uses_configured_host(tmp_path: Path, monkeypatch) -> None:
    entitlements_path = tmp_path / "Planini.entitlements"
    monkeypatch.setattr(tasks, "IOS_ENTITLEMENTS_PATH", entitlements_path)

    tasks._write_ios_entitlements("example.com")

    assert "webcredentials:example.com" in entitlements_path.read_text(encoding="utf-8")


def test_configure_ios_app_updates_project_and_entitlements(monkeypatch, tmp_path: Path) -> None:
    project_path = tmp_path / "project.yml"
    project_path.write_text(
        "\n".join(
            [
                "PRODUCT_BUNDLE_IDENTIFIER: com.example.old",
                "DEVELOPMENT_TEAM: OLDTEAM123",
                "INFOPLIST_KEY_PlaniniBackendBaseURL: https://old.example.com",
                "",
            ]
        ),
        encoding="utf-8",
    )
    entitlements_path = tmp_path / "Planini.entitlements"
    generated_config_path = tmp_path / "BuildConfiguration.generated.swift"
    calls: list[str] = []

    monkeypatch.setattr(tasks, "IOS_PROJECT_YML_PATH", project_path)
    monkeypatch.setattr(tasks, "IOS_ENTITLEMENTS_PATH", entitlements_path)
    monkeypatch.setattr(tasks, "IOS_GENERATED_CONFIG_PATH", generated_config_path)
    monkeypatch.setattr(tasks.install_xcodegen, "body", lambda c: calls.append("install_xcodegen"))
    monkeypatch.setattr(
        tasks.generate_ios_project, "body", lambda c: calls.append("generate_ios_project")
    )

    tasks.configure_ios_app.body(
        None,
        backend_url="https://selfhost.example.com",
        passkey_domain="passkeys.example.com",
        bundle_id="com.example.selfhost",
        development_team="NEWTEAM456",
        regenerate_project=True,
    )

    project_contents = project_path.read_text(encoding="utf-8")
    assert "PRODUCT_BUNDLE_IDENTIFIER: com.example.selfhost" in project_contents
    assert "DEVELOPMENT_TEAM: NEWTEAM456" in project_contents
    assert "INFOPLIST_KEY_PlaniniBackendBaseURL: https://selfhost.example.com" in project_contents
    assert "webcredentials:passkeys.example.com" in entitlements_path.read_text(encoding="utf-8")
    assert (
        'static let backendURL = "https://selfhost.example.com"'
        in generated_config_path.read_text(encoding="utf-8")
    )
    assert calls == ["install_xcodegen", "generate_ios_project"]


def test_start_ios_backend_derives_rp_id_from_backend_url(monkeypatch) -> None:
    calls: list[dict] = []

    monkeypatch.setattr(tasks, "start_app", lambda c, **kwargs: calls.append(kwargs))

    tasks.start_ios_backend.body(
        None,
        backend_url="https://shopping.example.com",
        seed_path="app/fixtures/review_seed_e2e.json",
        database_url="sqlite+aiosqlite:///./tmp-ios-e2e.db",
        host="127.0.0.1",
        port=8017,
        log_path="ios-e2e-server.log",
        pid_path="ios-e2e-server.pid",
    )

    assert calls == [
        {
            "seed_path": "app/fixtures/review_seed_e2e.json",
            "database_url": "sqlite+aiosqlite:///./tmp-ios-e2e.db",
            "webauthn_rp_id": "shopping.example.com",
            "host": "127.0.0.1",
            "port": 8017,
            "log_path": "ios-e2e-server.log",
            "pid_path": "ios-e2e-server.pid",
        }
    ]


def test_check_ios_package_invokes_swift_test(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0)

    monkeypatch.setattr(
        tasks,
        "_ios_toolchain_env",
        lambda: {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
    )

    tasks.check_ios_package.body(Context(), package_path="ios/PlaniniIOS")

    assert calls == [
        (
            "xcrun swift test --package-path ios/PlaniniIOS --enable-code-coverage",
            {
                "env": {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
                "pty": False,
                "shell": "/bin/bash",
            },
        )
    ]


def test_generate_ios_project_invokes_xcodegen() -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0)

    tasks.generate_ios_project.body(Context(), project_dir="ios/PlaniniIOS")

    assert calls == [
        (
            "cd ios/PlaniniIOS && xcodegen generate",
            {
                "pty": False,
                "shell": "/bin/bash",
            },
        )
    ]


def test_install_xcodegen_invokes_brew() -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0)

    tasks.install_xcodegen.body(Context())

    assert calls == [
        (
            "brew list xcodegen >/dev/null 2>&1 || brew install xcodegen",
            {
                "pty": False,
                "shell": "/bin/bash",
            },
        )
    ]


def test_build_ios_simulator_invokes_xcodebuild(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0)

    monkeypatch.setattr(
        tasks,
        "_ios_toolchain_env",
        lambda: {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
    )

    tasks.build_ios_simulator.body(
        Context(),
        project_dir="ios/PlaniniIOS",
        scheme="Planini",
        configuration="Debug",
        destination="generic/platform=iOS Simulator",
    )

    assert calls == [
        (
            "cd ios/PlaniniIOS && "
            "xcodebuild -project PlaniniApp.xcodeproj "
            "-scheme Planini "
            "-configuration Debug "
            "-destination 'generic/platform=iOS Simulator' "
            "-quiet "
            "CODE_SIGNING_ALLOWED=NO build",
            {
                "env": {"DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"},
                "pty": False,
                "shell": "/bin/bash",
            },
        )
    ]


def test_run_ios_e2e_invokes_swift_test_with_expected_env(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0)

    monkeypatch.setattr(
        tasks,
        "_ios_e2e_env",
        lambda **kwargs: {
            "PLANINI_E2E_BASE_URL": kwargs["base_url"],
            "PLANINI_E2E_SEED_PATH": kwargs["e2e_seed_path"],
            "PLANINI_E2E_RP_ID": kwargs["webauthn_rp_id"],
            "PLANINI_E2E_USER_EMAIL": kwargs["user_email"],
            "PLANINI_E2E_ORIGIN": kwargs["origin"],
        },
    )

    tasks.run_ios_e2e.body(
        Context(),
        base_url="http://localhost:8017",
        e2e_seed_path="app/fixtures/review_seed_e2e.json",
        webauthn_rp_id="localhost",
        user_email="ios@example.com",
        origin="https://passkeys.example.com",
    )

    assert calls == [
        (
            "xcrun swift test --package-path ios/PlaniniIOS --filter LiveBackendE2ETests",
            {
                "env": {
                    "PLANINI_E2E_BASE_URL": "http://localhost:8017",
                    "PLANINI_E2E_SEED_PATH": "app/fixtures/review_seed_e2e.json",
                    "PLANINI_E2E_RP_ID": "localhost",
                    "PLANINI_E2E_USER_EMAIL": "ios@example.com",
                    "PLANINI_E2E_ORIGIN": "https://passkeys.example.com",
                },
                "pty": False,
                "shell": "/bin/bash",
            },
        )
    ]


def test_run_ios_ui_e2e_invokes_xcodebuild_with_expected_env(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, dict]] = []

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return RunResult(exited=0)

    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    artifact_path = tmp_path / "e2e-artifacts" / "ios-ui-e2e"
    result_bundle_path = artifact_path / tasks.DEFAULT_IOS_UI_E2E_RESULT_BUNDLE
    result_bundle_path.mkdir(parents=True)
    monkeypatch.setattr(
        tasks,
        "_ios_ui_test_env",
        lambda **kwargs: {
            "PLANINI_UI_TEST_BASE_URL": kwargs["base_url"],
            "PLANINI_UI_TEST_BOOTSTRAP_BASE_URL": kwargs["bootstrap_base_url"],
            "PLANINI_UI_TEST_USER_EMAIL": kwargs["user_email"],
            "PLANINI_UI_TEST_ARTIFACT_DIR": kwargs["artifact_dir"],
            "PLANINI_UI_TEST_INITIAL_LIST_NAME": kwargs["initial_list_name"],
            "PLANINI_UI_TEST_ACCESS_TOKEN": kwargs["access_token"],
            "PLANINI_UI_TEST_DISPLAY_NAME": kwargs["display_name"],
        },
    )
    summaries: list[str] = []
    monkeypatch.setattr(
        tasks, "_write_ios_ui_e2e_summary", lambda artifact_dir: summaries.append(artifact_dir)
    )

    tasks.run_ios_ui_e2e.body(
        Context(),
        base_url="http://localhost:8018",
        bootstrap_base_url="http://127.0.0.1:8018",
        user_email="ios@example.com",
        artifact_dir="e2e-artifacts/ios-ui-e2e",
        device_name="iPhone 17",
        initial_list_name="Browser Test Shop",
        access_token="token-123",
        display_name="Test User",
    )

    assert calls == [
        (
            "cd ios/PlaniniIOS && xcodebuild -project PlaniniApp.xcodeproj "
            "-scheme Planini -destination 'platform=iOS Simulator,name=iPhone 17' "
            f"-resultBundlePath {str(result_bundle_path.resolve())} -quiet "
            "-only-testing:PlaniniUITests test",
            {
                "env": {
                    "PLANINI_UI_TEST_BASE_URL": "http://localhost:8018",
                    "PLANINI_UI_TEST_BOOTSTRAP_BASE_URL": "http://127.0.0.1:8018",
                    "PLANINI_UI_TEST_USER_EMAIL": "ios@example.com",
                    "PLANINI_UI_TEST_ARTIFACT_DIR": "e2e-artifacts/ios-ui-e2e",
                    "PLANINI_UI_TEST_INITIAL_LIST_NAME": "Browser Test Shop",
                    "PLANINI_UI_TEST_ACCESS_TOKEN": "token-123",
                    "PLANINI_UI_TEST_DISPLAY_NAME": "Test User",
                },
                "pty": False,
                "shell": "/bin/bash",
                "warn": True,
            },
        )
    ]
    assert summaries == ["e2e-artifacts/ios-ui-e2e"]
    assert not result_bundle_path.exists()


def test_run_ios_ui_e2e_retries_once_before_succeeding(monkeypatch, tmp_path: Path, capsys) -> None:
    calls: list[tuple[str, dict]] = []
    results = iter([RunResult(exited=65), RunResult(exited=0)])

    class Context:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            return next(results)

    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    monkeypatch.setattr(tasks, "_ios_ui_test_env", lambda **kwargs: {})
    monkeypatch.setattr(tasks, "_write_ios_ui_e2e_summary", lambda artifact_dir: None)

    tasks.run_ios_ui_e2e.body(Context(), artifact_dir="e2e-artifacts/ios-ui-e2e")

    assert len(calls) == 2
    assert (
        capsys.readouterr().out.count("Retrying iOS UI e2e after an initial xcodebuild failure...")
        == 1
    )


def test_run_ios_ui_e2e_prints_failure_summary_before_exiting(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    class Context:
        def run(self, command, **kwargs):
            return RunResult(exited=65)

    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    monkeypatch.setattr(tasks, "_ios_ui_test_env", lambda **kwargs: {})
    monkeypatch.setattr(tasks, "_write_ios_ui_e2e_summary", lambda artifact_dir: None)
    monkeypatch.setattr(
        tasks,
        "_ios_ui_e2e_failure_summaries",
        lambda result_bundle_path: ["testListViewFlow() [Failure]: Timed out waiting for response"],
    )

    try:
        tasks.run_ios_ui_e2e.body(Context(), artifact_dir="e2e-artifacts/ios-ui-e2e")
    except tasks.Exit as exc:
        assert "exit code 65" in str(exc)
    else:
        raise AssertionError("expected run_ios_ui_e2e to fail")

    captured = capsys.readouterr()
    assert captured.out.count("Retrying iOS UI e2e after an initial xcodebuild failure...") == 1
    assert "iOS UI e2e failure summary:" in captured.out
    assert "testListViewFlow() [Failure]: Timed out waiting for response" in captured.out


def test_check_ios_e2e_starts_waits_runs_and_stops(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        tasks,
        "_reset_sqlite_database_file",
        lambda database_url: calls.append(("reset", {"database_url": database_url})),
    )
    monkeypatch.setattr(tasks, "start_app", lambda c, **kwargs: calls.append(("start", kwargs)))
    monkeypatch.setattr(tasks, "wait_for_app", lambda c, **kwargs: calls.append(("wait", kwargs)))
    monkeypatch.setattr(tasks, "run_ios_e2e", lambda c, **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(tasks, "stop_app", lambda c, **kwargs: calls.append(("stop", kwargs)))

    tasks.check_ios_e2e.body(
        None,
        seed_path="app/fixtures/review_seed_e2e.json",
        e2e_seed_path="app/fixtures/review_seed_e2e.json",
        database_url="sqlite+aiosqlite:///./tmp-ios-e2e.db",
        webauthn_rp_id="localhost",
        user_email="ios@example.com",
        origin="https://passkeys.example.com",
        host="127.0.0.1",
        port=8017,
        log_path="ios-e2e-server.log",
        pid_path="ios-e2e-server.pid",
    )

    assert calls == [
        ("reset", {"database_url": "sqlite+aiosqlite:///./tmp-ios-e2e.db"}),
        (
            "start",
            {
                "seed_path": "app/fixtures/review_seed_e2e.json",
                "database_url": "sqlite+aiosqlite:///./tmp-ios-e2e.db",
                "webauthn_rp_id": "localhost",
                "host": "127.0.0.1",
                "port": 8017,
                "log_path": "ios-e2e-server.log",
                "pid_path": "ios-e2e-server.pid",
            },
        ),
        ("wait", {"url": "http://127.0.0.1:8017/health"}),
        (
            "run",
            {
                "base_url": "http://127.0.0.1:8017",
                "e2e_seed_path": "app/fixtures/review_seed_e2e.json",
                "webauthn_rp_id": "localhost",
                "user_email": "ios@example.com",
                "origin": "https://passkeys.example.com",
            },
        ),
        ("stop", {"pid_path": "ios-e2e-server.pid"}),
    ]


def test_check_ios_ui_e2e_starts_waits_runs_and_stops(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        tasks,
        "_reset_sqlite_database_file",
        lambda database_url: calls.append(("reset", {"database_url": database_url})),
    )
    monkeypatch.setattr(tasks, "start_app", lambda c, **kwargs: calls.append(("start", kwargs)))
    monkeypatch.setattr(tasks, "wait_for_app", lambda c, **kwargs: calls.append(("wait", kwargs)))
    monkeypatch.setattr(
        tasks,
        "_bootstrap_ios_ui_test_session",
        lambda **kwargs: calls.append(("bootstrap", kwargs))
        or {"access_token": "token-123", "display_name": "Test User"},
    )
    monkeypatch.setattr(
        tasks.generate_ios_project, "body", lambda c: calls.append(("generate", {}))
    )
    monkeypatch.setattr(tasks, "run_ios_ui_e2e", lambda c, **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(tasks, "stop_app", lambda c, **kwargs: calls.append(("stop", kwargs)))

    tasks.check_ios_ui_e2e.body(
        None,
        seed_path="app/fixtures/review_seed_e2e.json",
        database_url="sqlite+aiosqlite:///./tmp-ios-ui-e2e.db",
        webauthn_rp_id="localhost",
        user_email="ios@example.com",
        artifact_dir="e2e-artifacts/ios-ui-e2e",
        device_name="iPhone 17",
        initial_list_name="Browser Test Shop",
        host="127.0.0.1",
        port=8018,
        log_path="ios-ui-e2e-server.log",
        pid_path="ios-ui-e2e-server.pid",
    )

    assert calls == [
        ("reset", {"database_url": "sqlite+aiosqlite:///./tmp-ios-ui-e2e.db"}),
        (
            "start",
            {
                "seed_path": "app/fixtures/review_seed_e2e.json",
                "database_url": "sqlite+aiosqlite:///./tmp-ios-ui-e2e.db",
                "webauthn_rp_id": "localhost",
                "host": "127.0.0.1",
                "port": 8018,
                "log_path": "ios-ui-e2e-server.log",
                "pid_path": "ios-ui-e2e-server.pid",
                "ui_test_bootstrap_enabled": True,
            },
        ),
        ("wait", {"url": "http://127.0.0.1:8018/health"}),
        (
            "bootstrap",
            {
                "base_url": "http://localhost:8018",
                "user_email": "ios@example.com",
            },
        ),
        ("generate", {}),
        (
            "run",
            {
                "base_url": "http://localhost:8018",
                "bootstrap_base_url": "http://127.0.0.1:8018",
                "user_email": "ios@example.com",
                "artifact_dir": "e2e-artifacts/ios-ui-e2e",
                "device_name": "iPhone 17",
                "initial_list_name": "Browser Test Shop",
                "access_token": "token-123",
                "display_name": "Test User",
            },
        ),
        ("stop", {"pid_path": "ios-ui-e2e-server.pid"}),
    ]


def test_install_deps_runs_python_and_js_bootstrap(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        tasks.setup_venv,
        "body",
        lambda c, python_bin="python3.14": calls.append(("setup_venv", python_bin)),
    )
    monkeypatch.setattr(
        tasks.install_js,
        "body",
        lambda c: calls.append(("install_js", None)),
    )
    monkeypatch.setattr(
        tasks.install_browser,
        "body",
        lambda c, with_deps=False: calls.append(("install_browser", with_deps)),
    )

    tasks.install_deps.body(
        None,
        python_bin="python3.13",
        with_browser=True,
        browser_with_deps=True,
    )

    assert calls == [
        ("setup_venv", "python3.13"),
        ("install_js", None),
        ("install_browser", True),
    ]
