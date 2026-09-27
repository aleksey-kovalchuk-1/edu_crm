"""Настройки → Резервное копирование (spec 2026-09-27-backup-settings), crm-superadmin only.

The API never touches backup files. It reads the status report that scripts/scheduled-backup.sh writes on the
Mac (mounted read-only) and, for a manual copy, drops a request flag that the host agent
scripts/run-requested-backup.sh picks up. No paths, downloads, restores or deletions."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import utcnow

router = APIRouter(prefix='/api/v1/backups', tags=['Резервное копирование'])
superadmin_only = require_roles(ROLE_SUPERADMIN)
SCHEMA = 1
STALE_AFTER = timedelta(hours=36)
RUN_TIMEOUT = timedelta(hours=6)  # a "running" report older than this belongs to an interrupted run


class FileOut(BaseModel):
    file: str
    size_bytes: int
    created_at: datetime


class PairOut(BaseModel):
    label: str
    database: FileOut | None
    attachments: FileOut | None


class LastRunOut(BaseModel):
    trigger: str
    label: str
    started_at: datetime
    finished_at: datetime | None
    result: str  # running | success | failure | interrupted
    verified: bool | None
    error: str | None


class RetentionOut(BaseModel):
    days: int
    min_pairs: int
    verification_configured: bool


class StatusOut(BaseModel):
    available: bool
    reason: str | None  # not_configured | no_report | damaged
    last_run: LastRunOut | None
    last_success_at: datetime | None
    stale: bool
    pairs: list[PairOut]
    retention: RetentionOut | None
    pending_request: bool
    pending_since: datetime | None  # when the waiting request (or its claim) appeared


def _dirs(request):
    settings = request.app.state.settings
    if not settings.backup_status_dir or not settings.backup_request_dir:
        return None, None
    return Path(settings.backup_status_dir), Path(settings.backup_request_dir)


def _parse(status_dir, now):
    """(reason, fields) — reason is None when the report is usable."""
    try:
        raw = json.loads((status_dir / 'status.json').read_text())
    except FileNotFoundError:
        return 'no_report', {}
    except (OSError, ValueError):
        return 'damaged', {}
    try:
        if raw.get('schema') != SCHEMA:
            raise ValueError('unknown schema')
        run = LastRunOut(**raw['last_run'])
        if run.result == 'running' and now - run.started_at > RUN_TIMEOUT:
            run.result = 'interrupted'
        return None, {
            'last_run': run,
            'last_success_at': raw.get('last_success_at'),
            'pairs': [PairOut(**pair) for pair in raw.get('pairs', [])],
            'retention': RetentionOut(**raw['retention']),
        }
    except (KeyError, TypeError, ValueError):
        return 'damaged', {}


def _mtime(path):
    try:
        return datetime.fromtimestamp(path.lstat().st_mtime, timezone.utc)
    except FileNotFoundError:
        return None


def _pending(request_dir, now):
    """(pending, since): a waiting request.json, or a claim the host agent took and has not finished."""
    requested = _mtime(request_dir / 'request.json')
    claimed = _mtime(request_dir / 'processing.json')
    if claimed is not None and now - claimed > RUN_TIMEOUT:
        claimed = None
    times = [t for t in (requested, claimed) if t is not None]
    return bool(times), (min(times) if times else None)


def _is_running(request_dir, fields, now):
    claimed = _mtime(request_dir / 'processing.json')
    if claimed is not None and now - claimed <= RUN_TIMEOUT:
        return True
    run = fields.get('last_run')
    return bool(run and run.result == 'running')


@router.get('/status', response_model=StatusOut, summary='Состояние резервного копирования',
            dependencies=[Depends(superadmin_only)])
def backup_status(request: Request):
    status_dir, request_dir = _dirs(request)
    empty = dict(last_run=None, last_success_at=None, stale=True, pairs=[], retention=None)
    if status_dir is None:
        return StatusOut(available=False, reason='not_configured', pending_request=False, pending_since=None, **empty)
    now = utcnow()
    pending, since = _pending(request_dir, now)
    reason, fields = _parse(status_dir, now)
    if reason:
        return StatusOut(available=False, reason=reason, pending_request=pending, pending_since=since, **empty)
    last_success = fields['last_success_at']
    stale = last_success is None or now - datetime.fromisoformat(str(last_success).replace('Z', '+00:00')) > STALE_AFTER
    return StatusOut(available=True, reason=None, stale=stale, pending_request=pending, pending_since=since, **fields)


class ManualOut(BaseModel):
    state: str


@router.post('/manual', response_model=ManualOut, status_code=202, summary='Запросить резервную копию сейчас')
def request_manual_backup(request: Request, auth: AuthContext = Depends(superadmin_only), db: Session = Depends(get_db)):
    status_dir, request_dir = _dirs(request)
    if status_dir is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Ручное резервное копирование не настроено на этом сервере')
    now = utcnow()
    _, fields = _parse(status_dir, now)
    if _is_running(request_dir, fields, now):
        raise AppError(ErrorCode.CONFLICT, 'Резервная копия уже создаётся — дождитесь окончания')
    flag = request_dir / 'request.json'
    payload = json.dumps({'requested_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'requested_by_user_id': auth.user.id})
    try:
        # O_EXCL: two quick clicks cannot create two requests.
        descriptor = os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise AppError(ErrorCode.CONFLICT, 'Резервная копия уже запрошена — дождитесь окончания')
    except OSError:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось передать запрос службе резервного копирования')
    with os.fdopen(descriptor, 'w') as out:
        out.write(payload)
    record_event(db, request, auth.user, 'backup.manual_requested', entity_type='backup',
                 summary='Запрошена ручная резервная копия', payload={})
    db.commit()
    return ManualOut(state='requested')
