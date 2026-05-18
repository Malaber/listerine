import asyncio
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import backups as backup_module
from app.services.backup_scheduler import start_backup_scheduler, stop_backup_scheduler
from app.services.backups import (
    BackupConfirmationError,
    BackupConfigurationError,
    BackupExecutionError,
    BackupNotFoundError,
    BackupSlot,
    configured_backup_slots,
    create_database_backup,
    delete_database_backup,
    list_database_backups,
    restore_database_backup,
    run_backup_slot,
    verify_database_backup,
)


def _sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


def test_create_database_backup_writes_sqlite_dump(tmp_path: Path) -> None:
    database_path = tmp_path / "planini.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE groceries (name TEXT NOT NULL)")
        connection.execute("INSERT INTO groceries (name) VALUES ('Milk')")

    result = create_database_backup(
        database_url=_sqlite_url(database_path),
        backup_directory=str(tmp_path / "backups"),
    )

    assert result.database == "sqlite"
    assert result.file_name.startswith("planini-sqlite-")
    assert result.file_name.endswith(".sql")
    assert result.size_bytes > 0
    dump = result.file_path.read_text(encoding="utf-8")
    assert "CREATE TABLE groceries" in dump
    assert "INSERT INTO \"groceries\" VALUES('Milk')" in dump


def test_list_delete_and_restore_sqlite_backup(tmp_path: Path) -> None:
    database_path = tmp_path / "planini.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE groceries (name TEXT NOT NULL)")
        connection.execute("INSERT INTO groceries (name) VALUES ('Milk')")

    backup = create_database_backup(
        database_url=_sqlite_url(database_path),
        backup_directory=str(tmp_path / "backups"),
    )
    backups = list_database_backups(backup_directory=str(tmp_path / "backups"))
    assert [entry.file_name for entry in backups] == [backup.file_name]
    assert backups[0].slot_name is None

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TABLE groceries")
        connection.execute("CREATE TABLE changed (name TEXT NOT NULL)")

    restored = restore_database_backup(
        backup.file_name,
        backup.file_name,
        database_url=_sqlite_url(database_path),
        backup_directory=str(tmp_path / "backups"),
    )
    assert restored.file_name == backup.file_name
    with sqlite3.connect(database_path) as connection:
        rows = list(connection.execute("SELECT name FROM groceries"))
    assert rows == [("Milk",)]

    deleted = delete_database_backup(
        backup.file_name,
        backup.file_name,
        backup_directory=str(tmp_path / "backups"),
    )
    assert deleted.file_name == backup.file_name
    assert backup.file_path.exists() is False


def test_backup_delete_requires_exact_confirmation(tmp_path: Path) -> None:
    with pytest.raises(BackupConfirmationError, match="exact backup filename"):
        delete_database_backup(
            "planini-sqlite-test.sql",
            "wrong.sql",
            backup_directory=str(tmp_path / "backups"),
        )


def test_backup_lookup_rejects_missing_or_unsafe_names(tmp_path: Path) -> None:
    with pytest.raises(BackupNotFoundError, match="path separators"):
        delete_database_backup(
            "../planini-sqlite-test.sql",
            "../planini-sqlite-test.sql",
            backup_directory=str(tmp_path / "backups"),
        )
    with pytest.raises(BackupNotFoundError, match="Backup file not found"):
        delete_database_backup(
            "planini-sqlite-missing.sql",
            "planini-sqlite-missing.sql",
            backup_directory=str(tmp_path / "backups"),
        )


def test_restore_sqlite_rejects_wrong_database_or_invalid_dump(tmp_path: Path) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    backup_path = backup_directory / "planini-sqlite-broken.sql"
    backup_path.write_text("not valid sql", encoding="utf-8")

    with pytest.raises(sqlite3.DatabaseError):
        restore_database_backup(
            backup_path.name,
            backup_path.name,
            database_url=_sqlite_url(tmp_path / "planini.db"),
            backup_directory=str(backup_directory),
        )
    with pytest.raises(BackupConfigurationError, match="file-backed"):
        restore_database_backup(
            backup_path.name,
            backup_path.name,
            database_url="sqlite+aiosqlite:///:memory:",
            backup_directory=str(backup_directory),
        )
    with pytest.raises(BackupConfigurationError, match="Cannot restore"):
        restore_database_backup(
            backup_path.name,
            backup_path.name,
            database_url="postgresql://user@example.com/planini",
            backup_directory=str(backup_directory),
        )


def test_run_backup_slot_verifies_new_backup_and_deletes_old_slot_file(tmp_path: Path) -> None:
    database_path = tmp_path / "planini.db"
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    old_backup = backup_directory / "planini-auto-slot-1--sqlite-20000101T000000Z-old.sql"
    old_backup.write_text("old", encoding="utf-8")
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE groceries (name TEXT NOT NULL)")

    result = run_backup_slot(
        "slot-1",
        database_url=_sqlite_url(database_path),
        backup_directory=str(backup_directory),
        raw_slots=["slot-1@00:00"],
    )

    assert result.slot_name == "slot-1"
    assert result.file_name.startswith("planini-auto-slot-1--sqlite-")
    assert result.file_path.exists()
    assert old_backup.exists() is False
    assert [
        entry.slot_name for entry in list_database_backups(backup_directory=str(backup_directory))
    ] == ["slot-1"]


def test_run_backup_slot_keeps_old_backup_when_verification_fails(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "planini.db"
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    old_backup = backup_directory / "planini-auto-slot-1--sqlite-20000101T000000Z-old.sql"
    old_backup.write_text("old", encoding="utf-8")
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE groceries (name TEXT NOT NULL)")

    def fail_verify(*args, **kwargs):
        raise BackupExecutionError("bad backup")

    monkeypatch.setattr("app.services.backups.verify_database_backup", fail_verify)

    with pytest.raises(BackupExecutionError, match="bad backup"):
        run_backup_slot(
            "slot-1",
            database_url=_sqlite_url(database_path),
            backup_directory=str(backup_directory),
            raw_slots=["slot-1@00:00"],
        )

    assert old_backup.exists()
    assert len(list(backup_directory.glob("planini-auto-slot-1--*.sql"))) == 1


def test_backup_slots_parse_and_report_due_state() -> None:
    slots = configured_backup_slots(["slot-1@01:00"])
    assert slots == [BackupSlot(name="slot-1", time="01:00")]
    assert slots[0].display_name == "Slot 1"
    assert slots[0].is_due(datetime(2026, 5, 18, 0, 59), None) is False
    assert slots[0].is_due(datetime(2026, 5, 18, 1, 0), None) is True
    assert slots[0].is_due(datetime(2026, 5, 18, 2, 0), "2026-05-18") is False
    assert (
        BackupSlot(name="slot-2", time="01:00", enabled=False).is_due(
            datetime(2026, 5, 18, 2, 0),
            None,
        )
        is False
    )


@pytest.mark.parametrize("entry", ["slot-1", "slot-1@bad", "Slot-1@01:00", "slot-1@24:00"])
def test_backup_slots_reject_invalid_entries(entry: str) -> None:
    with pytest.raises(BackupConfigurationError):
        configured_backup_slots([entry])


def test_run_backup_slot_requires_configured_slot(tmp_path: Path) -> None:
    with pytest.raises(BackupConfigurationError, match="not configured"):
        run_backup_slot(
            "slot-2", backup_directory=str(tmp_path / "backups"), raw_slots=["slot-1@01:00"]
        )


def test_delete_previous_slot_backups_ignores_manual_backups(tmp_path: Path) -> None:
    database_path = tmp_path / "planini.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE groceries (name TEXT NOT NULL)")
    result = create_database_backup(
        database_url=_sqlite_url(database_path),
        backup_directory=str(tmp_path / "backups"),
    )

    backup_module._delete_previous_slot_backups(result)

    assert result.file_path.exists()


def test_create_database_backup_requires_configured_backup_directory(tmp_path: Path) -> None:
    with pytest.raises(BackupConfigurationError, match="BACKUP_DIRECTORY must be configured"):
        create_database_backup(
            database_url=_sqlite_url(tmp_path / "planini.db"),
            backup_directory="",
        )


def test_create_database_backup_rejects_non_directory_backup_path(tmp_path: Path) -> None:
    backup_path = tmp_path / "backup-file"
    backup_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(BackupConfigurationError, match="Backup path is not a directory"):
        create_database_backup(
            database_url=_sqlite_url(tmp_path / "planini.db"),
            backup_directory=str(backup_path),
        )


def test_create_database_backup_rejects_unwritable_backup_directory(
    tmp_path: Path, monkeypatch
) -> None:
    def fail_write_test(**kwargs):
        raise OSError("read-only")

    monkeypatch.setattr("app.services.backups.tempfile.NamedTemporaryFile", fail_write_test)

    with pytest.raises(BackupConfigurationError, match="Backup directory is not writable"):
        create_database_backup(
            database_url=_sqlite_url(tmp_path / "planini.db"),
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_requires_file_backed_sqlite(tmp_path: Path) -> None:
    with pytest.raises(BackupConfigurationError, match="file-backed database"):
        create_database_backup(
            database_url="sqlite+aiosqlite:///:memory:",
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_rejects_missing_sqlite_file(tmp_path: Path) -> None:
    with pytest.raises(BackupConfigurationError, match="SQLite database file does not exist"):
        create_database_backup(
            database_url=_sqlite_url(tmp_path / "missing.db"),
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_rejects_unsupported_database(tmp_path: Path) -> None:
    with pytest.raises(BackupConfigurationError, match="do not support 'mysql'"):
        create_database_backup(
            database_url="mysql://user@example.com/planini",
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_runs_pg_dump(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[3]).write_bytes(b"pg dump")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    result = create_database_backup(
        database_url="postgresql+asyncpg://user:secret@example.com/planini",
        backup_directory=str(tmp_path / "backups"),
        pg_dump_command="custom-pg-dump",
    )

    assert result.database == "postgresql"
    assert result.file_name.startswith("planini-postgresql-")
    assert result.file_name.endswith(".pgdump")
    assert result.size_bytes == len(b"pg dump")
    assert calls == [
        (
            [
                "custom-pg-dump",
                "--format=custom",
                "--file",
                str(result.file_path),
                "postgresql://user:secret@example.com/planini",
            ],
            {
                "capture_output": True,
                "check": False,
                "text": True,
                "timeout": 120,
            },
        )
    ]


def test_create_database_backup_reports_pg_dump_failure(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    with pytest.raises(BackupExecutionError, match="pg_dump failed: permission denied"):
        create_database_backup(
            database_url="postgresql://user@example.com/planini",
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_reports_pg_dump_stdout_failure(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="connection failed", stderr="")

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    with pytest.raises(BackupExecutionError, match="pg_dump failed: connection failed"):
        create_database_backup(
            database_url="postgresql://user@example.com/planini",
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_reports_pg_dump_failure_without_output(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    with pytest.raises(BackupExecutionError, match="pg_dump failed: pg_dump failed"):
        create_database_backup(
            database_url="postgresql://user@example.com/planini",
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_reports_missing_pg_dump(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    with pytest.raises(BackupExecutionError, match="pg_dump command not found: pg_dump"):
        create_database_backup(
            database_url="postgresql://user@example.com/planini",
            backup_directory=str(tmp_path / "backups"),
        )


def test_create_database_backup_reports_pg_dump_timeout(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired("pg_dump", 120)

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    with pytest.raises(BackupExecutionError, match="pg_dump timed out"):
        create_database_backup(
            database_url="postgresql://user@example.com/planini",
            backup_directory=str(tmp_path / "backups"),
        )


def test_verify_and_restore_postgresql_backup_run_pg_restore(tmp_path: Path, monkeypatch) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    backup_path = backup_directory / "planini-postgresql-20260518T010000Z-test.pgdump"
    backup_path.write_bytes(b"pg dump")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.services.backups.subprocess.run", fake_run)

    verified = verify_database_backup(
        backup_path.name,
        backup_directory=str(backup_directory),
        pg_restore_command="custom-pg-restore",
    )
    restored = restore_database_backup(
        backup_path.name,
        backup_path.name,
        database_url="postgresql+asyncpg://user:secret@example.com/planini",
        backup_directory=str(backup_directory),
        pg_restore_command="custom-pg-restore",
    )

    assert verified.file_name == backup_path.name
    assert restored.database == "postgresql"
    assert calls == [
        ["custom-pg-restore", "--list", str(backup_path)],
        [
            "custom-pg-restore",
            "--clean",
            "--if-exists",
            "--dbname",
            "postgresql://user:secret@example.com/planini",
            str(backup_path),
        ],
    ]


def test_verify_postgresql_backup_reports_pg_restore_errors(tmp_path: Path, monkeypatch) -> None:
    backup_directory = tmp_path / "backups"
    backup_directory.mkdir()
    backup_path = backup_directory / "planini-postgresql-20260518T010000Z-test.pgdump"
    backup_path.write_bytes(b"pg dump")

    def fail_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="bad archive", stderr="")

    monkeypatch.setattr("app.services.backups.subprocess.run", fail_run)
    with pytest.raises(BackupExecutionError, match="pg_restore verification failed: bad archive"):
        verify_database_backup(backup_path.name, backup_directory=str(backup_directory))

    def missing_run(command, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("app.services.backups.subprocess.run", missing_run)
    with pytest.raises(BackupExecutionError, match="pg_restore command not found"):
        verify_database_backup(backup_path.name, backup_directory=str(backup_directory))

    def timeout_run(command, **kwargs):
        raise subprocess.TimeoutExpired("pg_restore", 120)

    monkeypatch.setattr("app.services.backups.subprocess.run", timeout_run)
    with pytest.raises(BackupExecutionError, match="pg_restore timed out"):
        verify_database_backup(backup_path.name, backup_directory=str(backup_directory))


async def test_backup_scheduler_start_and_stop(monkeypatch) -> None:
    async def fake_loop() -> None:
        return None

    monkeypatch.setattr(
        "app.services.backup_scheduler.configured_backup_slots",
        lambda: [BackupSlot(name="slot-1", time="01:00")],
    )
    monkeypatch.setattr("app.services.backup_scheduler._backup_scheduler_loop", fake_loop)

    task = start_backup_scheduler()
    assert task is not None
    await task
    await stop_backup_scheduler(None)

    sleeper = asyncio.create_task(asyncio.sleep(60))
    await stop_backup_scheduler(sleeper)
    assert sleeper.cancelled()


def test_backup_scheduler_skips_when_no_slots() -> None:
    assert start_backup_scheduler() is None
