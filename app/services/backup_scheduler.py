import asyncio
import contextlib
from datetime import datetime

from app.services.backups import BackupError, configured_backup_slots, run_backup_slot


def start_backup_scheduler() -> asyncio.Task | None:
    if not configured_backup_slots():
        return None
    return asyncio.create_task(_backup_scheduler_loop())


async def stop_backup_scheduler(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _backup_scheduler_loop() -> None:  # pragma: no cover - infinite runtime loop.
    last_run_dates: dict[str, str] = {}
    while True:
        now = datetime.now()
        for slot in configured_backup_slots():
            if slot.is_due(now, last_run_dates.get(slot.name)):
                try:
                    await asyncio.to_thread(run_backup_slot, slot.name)
                except BackupError:
                    pass
                else:
                    last_run_dates[slot.name] = now.date().isoformat()
        await asyncio.sleep(60)
