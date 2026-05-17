import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.core.config import settings


class BackupError(RuntimeError):
    """Base error for database backup failures."""


class BackupConfigurationError(BackupError):
    """Raised when backup settings or database URLs are unusable."""


class BackupExecutionError(BackupError):
    """Raised when a configured backup command fails."""


@dataclass(frozen=True)
class BackupResult:
    file_path: Path
    file_name: str
    database: str
    size_bytes: int
    created_at: datetime


def create_database_backup(
    *,
    database_url: str | None = None,
    backup_directory: str | None = None,
    pg_dump_command: str | None = None,
) -> BackupResult:
    resolved_database_url = database_url or settings.database_url
    resolved_backup_directory = (
        settings.backup_directory if backup_directory is None else backup_directory
    )
    resolved_pg_dump_command = pg_dump_command or settings.pg_dump_command

    destination_directory = _prepare_backup_directory(resolved_backup_directory)
    url = make_url(resolved_database_url)
    driver = url.drivername.partition("+")[0]

    if driver == "sqlite":
        return _create_sqlite_backup(url.database, destination_directory)
    if driver == "postgresql":
        return _create_postgresql_backup(url, destination_directory, resolved_pg_dump_command)
    raise BackupConfigurationError(f"Database backups do not support {url.drivername!r}.")


def _prepare_backup_directory(raw_directory: str | None) -> Path:
    if raw_directory is None or not raw_directory.strip():
        raise BackupConfigurationError("BACKUP_DIRECTORY must be configured.")

    directory = Path(raw_directory).expanduser().resolve()
    if directory.exists() and not directory.is_dir():
        raise BackupConfigurationError(f"Backup path is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.NamedTemporaryFile(
            dir=directory,
            prefix=".planini-backup-write-test-",
            delete=True,
        ):
            pass
    except OSError as exc:
        raise BackupConfigurationError(f"Backup directory is not writable: {directory}") from exc

    return directory


def _create_sqlite_backup(database_path: str | None, backup_directory: Path) -> BackupResult:
    if database_path in {None, "", ":memory:"}:
        raise BackupConfigurationError("SQLite backups require a file-backed database.")

    source_path = Path(database_path).expanduser().resolve()
    if not source_path.exists():
        raise BackupConfigurationError(f"SQLite database file does not exist: {source_path}")

    created_at = datetime.now(UTC)
    destination = _backup_file_path(backup_directory, "sqlite", "sql", created_at)
    database_uri = f"{source_path.as_uri()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        with destination.open("w", encoding="utf-8") as output:
            for line in connection.iterdump():
                output.write(f"{line}\n")

    return _result(destination, "sqlite", created_at)


def _create_postgresql_backup(url, backup_directory: Path, pg_dump_command: str) -> BackupResult:
    created_at = datetime.now(UTC)
    destination = _backup_file_path(backup_directory, "postgresql", "pgdump", created_at)
    sync_url = url.set(drivername="postgresql")
    command = [
        pg_dump_command,
        "--format=custom",
        "--file",
        str(destination),
        sync_url.render_as_string(hide_password=False),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise BackupExecutionError(f"pg_dump command not found: {pg_dump_command}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupExecutionError("pg_dump timed out after 120 seconds.") from exc

    if completed.returncode != 0:
        detail = _pg_dump_error_detail(completed.stderr, completed.stdout)
        raise BackupExecutionError(f"pg_dump failed: {detail}")

    return _result(destination, "postgresql", created_at)


def _backup_file_path(
    backup_directory: Path,
    database: str,
    extension: str,
    created_at: datetime,
) -> Path:
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    return backup_directory / f"planini-{database}-{timestamp}-{suffix}.{extension}"


def _pg_dump_error_detail(stderr: str, stdout: str) -> str:
    for value in (stderr, stdout):
        detail = value.strip()
        if detail:
            return detail
    return "pg_dump failed"


def _result(destination: Path, database: str, created_at: datetime) -> BackupResult:
    return BackupResult(
        file_path=destination,
        file_name=destination.name,
        database=database,
        size_bytes=destination.stat().st_size,
        created_at=created_at,
    )
