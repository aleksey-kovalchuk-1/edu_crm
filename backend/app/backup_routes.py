"""Superadmin-only readout of host-published, sanitized encrypted-backup metadata.

`GET ''` returns the pair history (status.json, written by scripts/record-backup-status.py). Beside it,
`GET /run` returns the latest run's state (last-run.json, written by scripts/record-backup-run.py, including
failed runs) and whether a manual request is waiting; `POST /manual` only drops a request flag that the host
agent scripts/run-requested-backup.sh picks up. No paths, downloads, restores or deletions.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import utcnow

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


RUN_SCHEMA = 1
RUN_TIMEOUT = timedelta(hours=6)  # a run still "running" after this belongs to an interrupted run


class LastRun(BaseModel):
    trigger: str
    label: str
    started_at: datetime
    finished_at: datetime | None
    result: str  # running | success | failure | interrupted
    error: str | None


class RunStatus(BaseModel):
    available: bool
    reason: str | None = None  # not_configured | unavailable
    last_run: LastRun | None
    pending_request: bool
    pending_since: datetime | None
    manual_available: bool


def _request_dir(request):
    folder = request.app.state.settings.backup_request_dir
    return Path(folder) if folder else None


def _mtime(path):
    try:
        return datetime.fromtimestamp(path.lstat().st_mtime, timezone.utc)
    except FileNotFoundError:
        return None


def _pending(request_dir, now):
    """(pending, since): a waiting request.json, or a claim the host agent took and has not finished."""
    if request_dir is None:
        return False, None
    requested = _mtime(request_dir / 'request.json')
    claimed = _mtime(request_dir / 'processing.json')
    if claimed is not None and now - claimed > RUN_TIMEOUT:
        claimed = None
    times = [t for t in (requested, claimed) if t is not None]
    return bool(times), (min(times) if times else None)


def _last_run(status_file, now):
    """(reason, last_run): reason is 'unavailable' when the report cannot be read or validated."""
    try:
        raw = json.loads((Path(status_file).parent / 'last-run.json').read_text(encoding='utf-8'))
        if raw.get('schema') != RUN_SCHEMA:
            raise ValueError('unknown schema')
        run = LastRun.model_validate(raw)
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, TypeError, AttributeError, ValidationError):
        return 'unavailable', None
    if run.result == 'running' and now - run.started_at > RUN_TIMEOUT:
        run.result = 'interrupted'
    return None, run


@router.get('/run', response_model=RunStatus, summary='Последний запуск резервного копирования')
def backup_run(request: Request, auth: AuthContext = Depends(superadmin)):
    del auth
    now = utcnow()
    request_dir = _request_dir(request)
    pending, since = _pending(request_dir, now)
    status_file = request.app.state.settings.backup_status_file
    if not status_file:
        return RunStatus(available=False, reason='not_configured', last_run=None, pending_request=pending,
                         pending_since=since, manual_available=request_dir is not None)
    reason, run = _last_run(status_file, now)
    return RunStatus(available=True, reason=reason, last_run=run, pending_request=pending, pending_since=since,
                     manual_available=request_dir is not None)


class ManualRequested(BaseModel):
    state: str


@router.post('/manual', response_model=ManualRequested, status_code=202, summary='Запросить резервную копию сейчас')
def request_manual_backup(request: Request, auth: AuthContext = Depends(superadmin), db: Session = Depends(get_db)):
    request_dir = _request_dir(request)
    if request_dir is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Ручное резервное копирование не настроено на этом сервере')
    now = utcnow()
    _, run = _last_run(request.app.state.settings.backup_status_file, now) if request.app.state.settings.backup_status_file else (None, None)
    claimed = _mtime(request_dir / 'processing.json')
    if (run is not None and run.result == 'running') or (claimed is not None and now - claimed <= RUN_TIMEOUT):
        raise AppError(ErrorCode.CONFLICT, 'Резервная копия уже создаётся — дождитесь окончания')
    payload = json.dumps({'requested_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'requested_by_user_id': auth.user.id})
    try:
        # O_EXCL: two quick clicks cannot create two requests.
        descriptor = os.open(request_dir / 'request.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise AppError(ErrorCode.CONFLICT, 'Резервная копия уже запрошена — дождитесь окончания')
    except OSError:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось передать запрос службе резервного копирования')
    with os.fdopen(descriptor, 'w') as out:
        out.write(payload)
    record_event(db, request, auth.user, 'backup.manual_requested', entity_type='backup',
                 summary='Запрошена ручная резервная копия', payload={})
    db.commit()
    return ManualRequested(state='requested')
