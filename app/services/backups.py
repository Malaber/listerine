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


class BackupNotFoundError(BackupError):
    """Raised when a named backup file cannot be found."""


class BackupConfirmationError(BackupError):
    """Raised when a destructive backup action is not confirmed."""


@dataclass(frozen=True)
class BackupResult:
    file_path: Path
    file_name: str
    database: str
    size_bytes: int
    created_at: datetime
    slot_name: str | None = None


@dataclass(frozen=True)
class BackupSlot:
    name: str
    time: str
    enabled: bool = True

    @property
    def display_name(self) -> str:
        return self.name.replace("-", " ").title()

    def is_due(self, now: datetime, last_run_date: str | None) -> bool:
        if not self.enabled:
            return False
        today = now.date().isoformat()
        if last_run_date == today:
            return False
        hour, minute = _parse_slot_time(self.time)
        return (now.hour, now.minute) >= (hour, minute)


def create_database_backup(
    *,
    database_url: str | None = None,
    backup_directory: str | None = None,
    pg_dump_command: str | None = None,
    slot_name: str | None = None,
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
        return _create_sqlite_backup(url.database, destination_directory, slot_name=slot_name)
    if driver == "postgresql":
        return _create_postgresql_backup(
            url,
            destination_directory,
            resolved_pg_dump_command,
            slot_name=slot_name,
        )
    raise BackupConfigurationError(f"Database backups do not support {url.drivername!r}.")


def list_database_backups(*, backup_directory: str | None = None) -> list[BackupResult]:
    destination_directory = _prepare_backup_directory(
        settings.backup_directory if backup_directory is None else backup_directory
    )
    backups = [
        _backup_entry(path)
        for extension in ("sql", "pgdump")
        for path in destination_directory.glob(f"planini-*.{extension}")
        if path.is_file()
    ]
    return sorted(backups, key=lambda backup: backup.created_at, reverse=True)


def delete_database_backup(
    file_name: str,
    confirmation_filename: str,
    *,
    backup_directory: str | None = None,
) -> BackupResult:
    _require_exact_filename(file_name, confirmation_filename)
    backup = _backup_by_name(file_name, backup_directory=backup_directory)
    backup.file_path.unlink()
    return backup


def restore_database_backup(
    file_name: str,
    confirmation_filename: str,
    *,
    database_url: str | None = None,
    backup_directory: str | None = None,
    pg_restore_command: str | None = None,
) -> BackupResult:
    _require_exact_filename(file_name, confirmation_filename)
    backup = _backup_by_name(file_name, backup_directory=backup_directory)
    url = make_url(database_url or settings.database_url)
    driver = url.drivername.partition("+")[0]
    if driver == "sqlite" and backup.database == "sqlite":
        _restore_sqlite_backup(backup.file_path, url.database)
        return backup
    if driver == "postgresql" and backup.database == "postgresql":
        _restore_postgresql_backup(
            backup.file_path,
            url,
            pg_restore_command or settings.pg_restore_command,
        )
        return backup
    raise BackupConfigurationError(
        f"Cannot restore {backup.database!r} backup into {url.drivername!r} database."
    )


def verify_database_backup(
    file_name: str,
    *,
    backup_directory: str | None = None,
    pg_restore_command: str | None = None,
) -> BackupResult:
    backup = _backup_by_name(file_name, backup_directory=backup_directory)
    if backup.database == "sqlite":
        _verify_sqlite_dump(backup.file_path)
        return backup
    _verify_postgresql_dump(backup.file_path, pg_restore_command or settings.pg_restore_command)
    return backup


def run_backup_slot(
    slot_name: str,
    *,
    database_url: str | None = None,
    backup_directory: str | None = None,
    pg_dump_command: str | None = None,
    pg_restore_command: str | None = None,
    raw_slots: list[str] | None = None,
) -> BackupResult:
    slot = _slot_by_name(slot_name, raw_slots=raw_slots)
    backup = create_database_backup(
        database_url=database_url,
        backup_directory=backup_directory,
        pg_dump_command=pg_dump_command,
        slot_name=slot.name,
    )
    try:
        verify_database_backup(
            backup.file_name,
            backup_directory=backup_directory,
            pg_restore_command=pg_restore_command,
        )
    except BackupError:
        backup.file_path.unlink(missing_ok=True)
        raise
    _delete_previous_slot_backups(backup)
    return backup


def configured_backup_slots(raw_slots: list[str] | None = None) -> list[BackupSlot]:
    entries = settings.backup_slots if raw_slots is None else raw_slots
    return [_parse_backup_slot(entry) for entry in entries]


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


def _create_sqlite_backup(
    database_path: str | None,
    backup_directory: Path,
    *,
    slot_name: str | None,
) -> BackupResult:
    if database_path in {None, "", ":memory:"}:
        raise BackupConfigurationError("SQLite backups require a file-backed database.")

    source_path = Path(database_path).expanduser().resolve()
    if not source_path.exists():
        raise BackupConfigurationError(f"SQLite database file does not exist: {source_path}")

    created_at = datetime.now(UTC)
    destination = _backup_file_path(
        backup_directory,
        "sqlite",
        "sql",
        created_at,
        slot_name=slot_name,
    )
    database_uri = f"{source_path.as_uri()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        with destination.open("w", encoding="utf-8") as output:
            for line in connection.iterdump():
                output.write(f"{line}\n")

    return _result(destination, "sqlite", created_at, slot_name=slot_name)


def _create_postgresql_backup(
    url,
    backup_directory: Path,
    pg_dump_command: str,
    *,
    slot_name: str | None,
) -> BackupResult:
    created_at = datetime.now(UTC)
    destination = _backup_file_path(
        backup_directory,
        "postgresql",
        "pgdump",
        created_at,
        slot_name=slot_name,
    )
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

    return _result(destination, "postgresql", created_at, slot_name=slot_name)


def _restore_sqlite_backup(backup_path: Path, database_path: str | None) -> None:
    if database_path in {None, "", ":memory:"}:
        raise BackupConfigurationError("SQLite restore requires a file-backed database.")

    target_path = Path(database_path).expanduser().resolve()
    restored_path = target_path.with_name(f".{target_path.name}.restore-{uuid4().hex}.tmp")
    try:
        with sqlite3.connect(restored_path) as connection:
            connection.executescript(backup_path.read_text(encoding="utf-8"))
        restored_path.replace(target_path)
        for suffix in ("-wal", "-shm"):
            target_path.with_name(f"{target_path.name}{suffix}").unlink(missing_ok=True)
    except Exception:
        restored_path.unlink(missing_ok=True)
        raise


def _restore_postgresql_backup(backup_path: Path, url, pg_restore_command: str) -> None:
    sync_url = url.set(drivername="postgresql")
    command = [
        pg_restore_command,
        "--clean",
        "--if-exists",
        "--dbname",
        sync_url.render_as_string(hide_password=False),
        str(backup_path),
    ]
    _run_postgres_restore_command(command, "pg_restore failed")


def _verify_sqlite_dump(backup_path: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as temp_database:
        with sqlite3.connect(temp_database.name) as connection:
            connection.executescript(backup_path.read_text(encoding="utf-8"))


def _verify_postgresql_dump(backup_path: Path, pg_restore_command: str) -> None:
    command = [pg_restore_command, "--list", str(backup_path)]
    _run_postgres_restore_command(command, "pg_restore verification failed")


def _run_postgres_restore_command(command: list[str], failure_prefix: str) -> None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise BackupExecutionError(f"pg_restore command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupExecutionError("pg_restore timed out after 120 seconds.") from exc

    if completed.returncode != 0:
        detail = _pg_dump_error_detail(completed.stderr, completed.stdout)
        raise BackupExecutionError(f"{failure_prefix}: {detail}")


def _backup_file_path(
    backup_directory: Path,
    database: str,
    extension: str,
    created_at: datetime,
    *,
    slot_name: str | None,
) -> Path:
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    if slot_name:
        safe_slot_name = _validate_slot_name(slot_name)
        return (
            backup_directory
            / f"planini-auto-{safe_slot_name}--{database}-{timestamp}-{suffix}.{extension}"
        )
    return backup_directory / f"planini-{database}-{timestamp}-{suffix}.{extension}"


def _pg_dump_error_detail(stderr: str, stdout: str) -> str:
    for value in (stderr, stdout):
        detail = value.strip()
        if detail:
            return detail
    return "pg_dump failed"


def _result(
    destination: Path,
    database: str,
    created_at: datetime,
    *,
    slot_name: str | None,
) -> BackupResult:
    return BackupResult(
        file_path=destination,
        file_name=destination.name,
        database=database,
        size_bytes=destination.stat().st_size,
        created_at=created_at,
        slot_name=slot_name,
    )


def _backup_entry(path: Path) -> BackupResult:
    database, slot_name = _parse_backup_file_name(path.name)
    return BackupResult(
        file_path=path,
        file_name=path.name,
        database=database,
        size_bytes=path.stat().st_size,
        created_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
        slot_name=slot_name,
    )


def _backup_by_name(file_name: str, *, backup_directory: str | None) -> BackupResult:
    if Path(file_name).name != file_name:
        raise BackupNotFoundError("Backup filename must not contain path separators.")
    destination_directory = _prepare_backup_directory(
        settings.backup_directory if backup_directory is None else backup_directory
    )
    path = destination_directory / file_name
    if not path.is_file():
        raise BackupNotFoundError(f"Backup file not found: {file_name}")
    return _backup_entry(path)


def _require_exact_filename(file_name: str, confirmation_filename: str) -> None:
    if confirmation_filename != file_name:
        raise BackupConfirmationError("Type the exact backup filename to confirm this action.")


def _parse_backup_file_name(file_name: str) -> tuple[str, str | None]:
    if file_name.startswith("planini-auto-"):
        slot_name, rest = file_name.removeprefix("planini-auto-").split("--", maxsplit=1)
        database = rest.split("-", maxsplit=1)[0]
        return database, slot_name
    return file_name.removeprefix("planini-").split("-", maxsplit=1)[0], None


def _delete_previous_slot_backups(backup: BackupResult) -> None:
    if backup.slot_name is None:
        return
    prefix = f"planini-auto-{backup.slot_name}--"
    for path in backup.file_path.parent.glob(f"{prefix}*"):
        if path != backup.file_path and path.is_file():
            path.unlink()


def _slot_by_name(slot_name: str, *, raw_slots: list[str] | None) -> BackupSlot:
    for slot in configured_backup_slots(raw_slots):
        if slot.name == slot_name:
            return slot
    raise BackupConfigurationError(f"Backup slot is not configured: {slot_name}")


def _parse_backup_slot(entry: str) -> BackupSlot:
    if "@" not in entry:
        raise BackupConfigurationError("Backup slots must use slot-name@HH:MM.")
    name, time = entry.split("@", maxsplit=1)
    name = _validate_slot_name(name)
    _parse_slot_time(time)
    return BackupSlot(name=name, time=time)


def _parse_slot_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise BackupConfigurationError("Backup slot time must use HH:MM.") from exc
    if hour not in range(24) or minute not in range(60):
        raise BackupConfigurationError("Backup slot time must use HH:MM.")
    return hour, minute


def _validate_slot_name(value: str) -> str:
    if not value or any(
        character not in "-_0123456789abcdefghijklmnopqrstuvwxyz" for character in value
    ):
        raise BackupConfigurationError(
            "Backup slot names may only use lowercase letters, numbers, hyphen, and underscore."
        )
    return value
