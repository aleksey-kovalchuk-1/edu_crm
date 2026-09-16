"""Generic background-job status endpoint (D-166). Not import-specific on purpose: report generation
(D-109) reuses `background_jobs` and this same endpoint later without a schema or API change.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import ALL_ROLES, AuthContext, require_roles
from .catalog_routes import PersonOut, sees_all
from .db import get_db
from .errors import AppError, ErrorCode
from .models import BackgroundJob, User

router = APIRouter(prefix='/api/v1/jobs', tags=['Фоновые задачи'])
any_role = require_roles(*ALL_ROLES)


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    payload: dict
    result: dict | None
    error: str | None
    correlation_id: str | None
    created_by: PersonOut | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.get('/{job_id}', response_model=JobOut, summary='Статус фоновой задачи')
def get_job(job_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    job = db.get(BackgroundJob, job_id)
    # A job belonging to someone else answers 404 (not 403), matching catalog_routes' "don't reveal
    # existence outside scope" convention for records outside a manager's data scope (D-141).
    if job is None or (not sees_all(auth.user) and job.created_by_user_id != auth.user.id):
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    creator = db.get(User, job.created_by_user_id) if job.created_by_user_id else None
    return JobOut(
        id=job.id, kind=job.kind, status=job.status, payload=job.payload, result=job.result, error=job.error,
        correlation_id=job.correlation_id, created_by=PersonOut(id=creator.id, full_name=creator.full_name) if creator else None,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
    )
