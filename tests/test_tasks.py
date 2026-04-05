import importlib
import sys
import types
from pathlib import Path

sys.modules.setdefault("invoke", types.SimpleNamespace(task=lambda fn: fn))
task_module = importlib.import_module("tasks")

_database_url_for_device = task_module._database_url_for_device
_reset_sqlite_database_file = task_module._reset_sqlite_database_file
_wait_for_pid_exit = task_module._wait_for_pid_exit
stop_app = task_module.stop_app


def test_database_url_for_device_uses_distinct_sqlite_file() -> None:
    database_url = "sqlite+aiosqlite:///./tmp-ci-ui-e2e.db"

    assert _database_url_for_device(database_url, "iphone") == (
        "sqlite+aiosqlite:///./tmp-ci-ui-e2e-iphone.db"
    )


def test_database_url_for_device_leaves_non_sqlite_urls_unchanged() -> None:
    database_url = "postgresql+asyncpg://user:password@example.com/listerine"

    assert _database_url_for_device(database_url, "iphone") == database_url


def test_reset_sqlite_database_file_removes_database_and_sidecars(tmp_path: Path) -> None:
    database_path = tmp_path / "browser-e2e.db"
    for suffix in ("", "-shm", "-wal"):
        database_path.with_name(f"{database_path.name}{suffix}").write_text(
            "data", encoding="utf-8"
        )

    _reset_sqlite_database_file(f"sqlite+aiosqlite:///{database_path}")

    for suffix in ("", "-shm", "-wal"):
        assert not database_path.with_name(f"{database_path.name}{suffix}").exists()


def test_wait_for_pid_exit_returns_once_process_is_gone(monkeypatch) -> None:
    states = iter([True, True, False])
    monkeypatch.setattr(task_module.os, "waitpid", lambda pid, flags: (0, 0))
    monkeypatch.setattr(task_module, "_pid_is_running", lambda pid: next(states))
    monkeypatch.setattr(task_module.time, "sleep", lambda _: None)

    _wait_for_pid_exit(123)


def test_wait_for_pid_exit_reaps_child_process(monkeypatch) -> None:
    monkeypatch.setattr(task_module.os, "waitpid", lambda pid, flags: (pid, 0))

    _wait_for_pid_exit(123)


def test_stop_app_waits_for_exit_before_removing_pid_file(tmp_path: Path, monkeypatch) -> None:
    pid_path = tmp_path / "ui-e2e-server.pid"
    pid_path.write_text("4321\n", encoding="utf-8")
    waits: list[tuple[int, float]] = []
    signals: list[tuple[int, int]] = []

    monkeypatch.setattr(task_module, "ROOT", tmp_path)
    monkeypatch.setattr(task_module, "_read_pid", lambda path: 4321)
    monkeypatch.setattr(
        task_module,
        "_wait_for_pid_exit",
        lambda pid, timeout_seconds=10.0: waits.append((pid, timeout_seconds)),
    )
    monkeypatch.setattr(task_module.os, "kill", lambda pid, sig: signals.append((pid, sig)))

    stop_app(None, pid_path=pid_path.name)

    assert signals == [(4321, task_module.signal.SIGTERM)]
    assert waits == [(4321, 10.0)]
    assert not pid_path.exists()
