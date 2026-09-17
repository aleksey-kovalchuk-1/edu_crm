"""Background-job handler for report generation (T-050-T-052, D-180-D-183).

Runs the same query and university scope (D-141) a live request would use, since the payload only
carries filters and the requesting user's id -- never a frozen list of allowed universities -- so a scope
change between enqueue and run is still respected.
"""
import secrets
from datetime import date
from pathlib import Path

from .jobs import JOB_HANDLERS
from .models import ReportFile, User
from .reports import CONTENT_TYPES, WRITERS, ReportFilters, build_rows
from .settings import load_settings


def run_report_generate(db, job, *, settings=None):
    settings = settings or load_settings()
    payload = job.payload
    user = db.get(User, job.created_by_user_id) if job.created_by_user_id else None
    if user is None:
        raise ValueError('report_generate job has no valid created_by_user_id')

    period_from = date.fromisoformat(payload['period_from']) if payload.get('period_from') else None
    period_to = date.fromisoformat(payload['period_to']) if payload.get('period_to') else None
    filters = ReportFilters(
        period_from=period_from, period_to=period_to,
        university_ids=payload.get('university_ids'), it_direction_ids=payload.get('it_direction_ids'),
        it_product_ids=payload.get('it_product_ids'), responsible=payload.get('responsible'),
        status_ids=payload.get('status_ids'), columns=payload.get('columns'),
    )
    rows = build_rows(db, user, filters)
    report_format = payload['format']
    content = WRITERS[report_format](rows, filters.columns, settings=settings)

    directory = Path(settings.reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    storage_key = secrets.token_hex(16)
    (directory / storage_key).write_bytes(content)

    db.add(ReportFile(
        job_id=job.id, format=report_format, storage_key=storage_key,
        filename=f'report-{job.id}.{report_format}', content_type=CONTENT_TYPES[report_format],
        size_bytes=len(content), created_by_user_id=user.id,
    ))
    db.commit()
    return {'rows': len(rows), 'format': report_format, 'columns': filters.columns}


JOB_HANDLERS['report_generate'] = run_report_generate
