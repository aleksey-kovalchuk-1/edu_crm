"""Superadmin-only readout of host-published, sanitized encrypted-backup metadata."""
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError

from .auth import ROLE_SUPERADMIN, AuthContext, require_roles

router = APIRouter(prefix='/api/v1/admin/backups', tags=['Резервное копирование'])
superadmin = require_roles(ROLE_SUPERADMIN)


class BackupItem(BaseModel):
    created_at: datetime
    source: str
    database_bytes: int
    attachments_bytes: int
    verified: bool


class BackupStatus(BaseModel):
    available: bool
    reason: str | None = None
    generated_at: datetime | None = None
    backups: list[BackupItem]


@router.get('', response_model=BackupStatus, summary='Статус зашифрованных резервных копий')
def backup_status(request: Request, auth: AuthContext = Depends(superadmin)):
    del auth
    filename = request.app.state.settings.backup_status_file
    if not filename:
        return BackupStatus(available=False, reason='not_configured', backups=[])
    try:
        raw = json.loads(Path(filename).read_text(encoding='utf-8'))
        status = BackupStatus.model_validate({**raw, 'available': True, 'reason': None})
        if any(item.database_bytes <= 0 or item.attachments_bytes <= 0 for item in status.backups):
            raise ValueError('invalid backup size')
        return status
    except FileNotFoundError:
        return BackupStatus(available=False, reason='missing', backups=[])
    except (OSError, ValueError, TypeError, ValidationError):
        return BackupStatus(available=False, reason='unavailable', backups=[])
