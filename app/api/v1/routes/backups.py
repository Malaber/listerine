import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import require_admin_user
from app.services.backups import (
    BackupConfigurationError,
    BackupExecutionError,
    BackupResult,
    create_database_backup,
)


class BackupOut(BaseModel):
    file_name: str
    path: str
    database: str
    size_bytes: int
    created_at: datetime


router = APIRouter(
    prefix="/admin/backups",
    tags=["admin"],
    dependencies=[Depends(require_admin_user)],
)


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


def _backup_out(result: BackupResult) -> BackupOut:
    return BackupOut(
        file_name=result.file_name,
        path=str(result.file_path),
        database=result.database,
        size_bytes=result.size_bytes,
        created_at=result.created_at,
    )
