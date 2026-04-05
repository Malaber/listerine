import importlib.util
from pathlib import Path

TASKS_PATH = Path(__file__).resolve().parents[1] / "tasks.py"
TASKS_SPEC = importlib.util.spec_from_file_location("tasks", TASKS_PATH)
assert TASKS_SPEC is not None
assert TASKS_SPEC.loader is not None
tasks = importlib.util.module_from_spec(TASKS_SPEC)
TASKS_SPEC.loader.exec_module(tasks)


def test_database_url_for_device_uses_distinct_sqlite_file() -> None:
    database_url = "sqlite+aiosqlite:///./tmp-ci-ui-e2e.db"

    assert tasks._database_url_for_device(database_url, "iphone") == (
        "sqlite+aiosqlite:///./tmp-ci-ui-e2e-iphone.db"
    )


def test_database_url_for_device_leaves_non_sqlite_urls_unchanged() -> None:
    database_url = "postgresql+asyncpg://user:password@example.com/listerine"

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


def test_wait_for_pid_exit_returns_once_process_is_gone(monkeypatch) -> None:
    states = iter([True, True, False])
    monkeypatch.setattr(tasks.os, "waitpid", lambda pid, flags: (0, 0))
    monkeypatch.setattr(tasks, "_pid_is_running", lambda pid: next(states))
    monkeypatch.setattr(tasks.time, "sleep", lambda _: None)

    tasks._wait_for_pid_exit(123)


def test_wait_for_pid_exit_reaps_child_process(monkeypatch) -> None:
    monkeypatch.setattr(tasks.os, "waitpid", lambda pid, flags: (pid, 0))

    tasks._wait_for_pid_exit(123)


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

    tasks.install_deps.body(None, python_bin="python3.13", with_browser=True, browser_with_deps=True)

    assert calls == [
        ("setup_venv", "python3.13"),
        ("install_js", None),
        ("install_browser", True),
    ]
