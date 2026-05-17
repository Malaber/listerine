import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.backups import (
    BackupConfigurationError,
    BackupExecutionError,
    create_database_backup,
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
