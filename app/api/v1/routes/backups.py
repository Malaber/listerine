import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import require_admin_user
from app.core.database import engine
from app.services.backups import (
    BackupConfirmationError,
    BackupConfigurationError,
    BackupExecutionError,
    BackupNotFoundError,
    BackupResult,
    create_database_backup,
    configured_backup_slots,
    delete_database_backup,
    list_database_backups,
    restore_database_backup,
    run_backup_slot,
)


class BackupOut(BaseModel):
    file_name: str
    path: str
    database: str
    size_bytes: int
    created_at: datetime
    slot_name: str | None = None


class BackupSlotOut(BaseModel):
    name: str
    display_name: str
    time: str
    enabled: bool


class BackupConfirmationIn(BaseModel):
    confirmation_filename: str


router = APIRouter(
    prefix="/admin/backups",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


@router.get("", response_model=list[BackupOut])
async def list_backups() -> list[BackupOut]:
    try:
        return [_backup_out(result) for result in await asyncio.to_thread(list_database_backups)]
    except BackupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.post("", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
async def create_backup() -> BackupOut:
    try:
        result = await asyncio.to_thread(create_database_backup)
    except BackupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except BackupExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return _backup_out(result)


@router.get("/slots", response_model=list[BackupSlotOut])
async def list_backup_slots() -> list[BackupSlotOut]:
    try:
        slots = configured_backup_slots()
    except BackupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return [
        BackupSlotOut(
            name=slot.name,
            display_name=slot.display_name,
            time=slot.time,
            enabled=slot.enabled,
        )
        for slot in slots
    ]


@router.post(
    "/slots/{slot_name}/run", response_model=BackupOut, status_code=status.HTTP_201_CREATED
)
async def run_slot_backup(slot_name: str) -> BackupOut:
    try:
        result = await asyncio.to_thread(run_backup_slot, slot_name)
    except BackupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except BackupExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    return _backup_out(result)


@router.delete("/{file_name}", response_model=BackupOut)
async def delete_backup(file_name: str, confirmation: BackupConfirmationIn) -> BackupOut:
    try:
        result = await asyncio.to_thread(
            delete_database_backup,
            file_name,
            confirmation.confirmation_filename,
        )
    except BackupConfirmationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BackupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return _backup_out(result)


@router.post("/{file_name}/restore", response_model=BackupOut)
async def restore_backup(file_name: str, confirmation: BackupConfirmationIn) -> BackupOut:
    try:
        result = await asyncio.to_thread(
            restore_database_backup,
            file_name,
            confirmation.confirmation_filename,
        )
    except BackupConfirmationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except BackupConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except BackupExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    await engine.dispose()
    return _backup_out(result)


def _backup_out(result: BackupResult) -> BackupOut:
    return BackupOut(
        file_name=result.file_name,
        path=str(result.file_path),
        database=result.database,
        size_bytes=result.size_bytes,
        created_at=result.created_at,
        slot_name=result.slot_name,
    )
