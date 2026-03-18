from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import close_all_sessions

from app.core.config import settings
from app.core.database import engine, run_migrations


async def dispose_db() -> None:
    await close_all_sessions()
    await engine.dispose()


async def reset_db() -> None:
    await dispose_db()

    database_url = make_url(settings.database_url)
    if database_url.drivername == "sqlite+aiosqlite" and database_url.database:
        database_path = Path(database_url.database)
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        for extra_suffix in ("", "-shm", "-wal"):
            sqlite_file = Path(f"{database_path}{extra_suffix}")
            if sqlite_file.exists():
                sqlite_file.unlink()

    await run_migrations()
