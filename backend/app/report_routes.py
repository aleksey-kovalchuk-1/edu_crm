"""Report generation API (T-050-T-054, D-180-D-183): filters and columns, an async job, and a download
endpoint. Job status is served by the existing generic `GET /api/v1/jobs/{id}` (D-166) -- no separate
status endpoint for reports.
"""
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import jobs
from .audit import record_event
from .auth import ALL_ROLES, AuthContext, require_roles
from .catalog_routes import sees_all
from .db import get_db
from .errors import AppError, ErrorCode
from .models import BackgroundJob, ReportFile
from .reports import REPORT_COLUMNS, REPORT_FORMATS

router = APIRouter(prefix='/api/v1/reports', tags=['Отчёты'])
any_role = require_roles(*ALL_ROLES)


def field_error(code, field, message):
    return AppError(code, message, [{'field': field, 'message': message, 'type': 'value_error'}])


class ReportRequest(BaseModel):
    period_from: date | None = None
    period_to: date | None = None
    university_ids: list[int] = Field(default_factory=list, max_length=200)
    it_direction_ids: list[int] = Field(default_factory=list, max_length=50)
    it_product_ids: list[int] = Field(default_factory=list, max_length=200)
    responsible: list[str] = Field(default_factory=list, max_length=50)
    status_ids: list[int] = Field(default_factory=list, max_length=200)
    columns: list[str] = Field(default_factory=list, max_length=len(REPORT_COLUMNS))
    format: Literal['xlsx', 'xls', 'pdf', 'json']


class ColumnOut(BaseModel):
    key: str
    label: str


class ReportJobOut(BaseModel):
    id: int
    status: str
    format: str
    created_at: datetime
    finished_at: datetime | None


@router.get('/columns', response_model=list[ColumnOut], summary='Доступные колонки отчёта', dependencies=[Depends(any_role)])
def list_columns():
    return [ColumnOut(key=key, label=label) for key, label in REPORT_COLUMNS.items()]


@router.get('', response_model=list[ReportJobOut], summary='Мои отчёты (и все — руководителю/администратору)')
def list_reports(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    query = select(BackgroundJob).where(BackgroundJob.kind == 'report_generate')
    if not sees_all(auth.user):
        query = query.where(BackgroundJob.created_by_user_id == auth.user.id)
    query = query.order_by(BackgroundJob.created_at.desc()).limit(50)
    jobs_list = db.scalars(query).all()
    return [
        ReportJobOut(id=job.id, status=job.status, format=job.payload.get('format', ''), created_at=job.created_at, finished_at=job.finished_at)
        for job in jobs_list
    ]


@router.post('', response_model=ReportJobOut, status_code=202, summary='Сформировать отчёт (асинхронно)')
def create_report(data: ReportRequest, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    if data.period_from and data.period_to and data.period_from > data.period_to:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'period_to', 'Конец периода раньше начала')
    unknown_columns = [c for c in data.columns if c not in REPORT_COLUMNS]
    if unknown_columns:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'columns', f'Неизвестные колонки: {", ".join(unknown_columns)}')

    payload = {
        'period_from': data.period_from.isoformat() if data.period_from else None,
        'period_to': data.period_to.isoformat() if data.period_to else None,
        'university_ids': data.university_ids,
        'it_direction_ids': data.it_direction_ids,
        'it_product_ids': data.it_product_ids,
        'responsible': data.responsible,
        'status_ids': data.status_ids,
        'columns': data.columns or list(REPORT_COLUMNS),
        'format': data.format,
    }
    job = jobs.enqueue(db, 'report_generate', payload, user_id=auth.user.id,
                        correlation_id=getattr(request.state, 'correlation_id', None))
    record_event(
        db, request, auth.user, 'report.generate', entity_type='report_job', entity_id=job.id,
        summary=f'Запрошен отчёт в формате {data.format}',
        payload={
            'format': data.format, 'columns': payload['columns'],
            'university_count': len(data.university_ids), 'status_count': len(data.status_ids),
            'it_direction_count': len(data.it_direction_ids), 'it_product_count': len(data.it_product_ids),
        },
    )
    db.commit()
    return ReportJobOut(id=job.id, status=job.status, format=data.format, created_at=job.created_at, finished_at=job.finished_at)


@router.get('/{job_id}/download', response_class=FileResponse, summary='Скачать готовый файл отчёта',
            responses={200: {'content': {'application/octet-stream': {}}}})
def download_report(job_id: int, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    job = db.get(BackgroundJob, job_id)
    # Someone else's report answers 404, not 403 (same "don't reveal existence outside scope" convention
    # as GET /jobs/{id} and the catalog endpoints, D-141).
    if job is None or job.kind != 'report_generate' or (not sees_all(auth.user) and job.created_by_user_id != auth.user.id):
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    if job.status in ('queued', 'running'):
        raise AppError(ErrorCode.CONFLICT, 'Отчёт ещё формируется')
    if job.status == 'failed':
        raise AppError(ErrorCode.CONFLICT, 'Формирование отчёта завершилось ошибкой')
    report_file = db.scalar(select(ReportFile).where(ReportFile.job_id == job_id))
    if report_file is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    path = Path(request.app.state.settings.reports_dir) / report_file.storage_key
    if not path.is_file():
        raise AppError(ErrorCode.RECORD_NOT_FOUND, 'Файл отчёта не найден в хранилище')
    record_event(db, request, auth.user, 'report.download', entity_type='report_job', entity_id=job.id,
                 summary=f'Скачан отчёт #{job.id} ({report_file.format})')
    db.commit()
    return FileResponse(path, media_type=report_file.content_type, filename=report_file.filename,
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})
