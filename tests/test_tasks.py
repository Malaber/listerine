import importlib
import sys
import types
from pathlib import Path

sys.modules.setdefault("invoke", types.SimpleNamespace(task=lambda fn: fn))
task_module = importlib.import_module("tasks")

_database_url_for_device = task_module._database_url_for_device
_reset_sqlite_database_file = task_module._reset_sqlite_database_file


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
