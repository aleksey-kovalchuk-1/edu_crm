"""Preview/apply customer imports and read-only course application cards."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import like_pattern, not_found
from .customer_imports import CustomerImportRunner, read_rows
from .db import get_db
from .errors import AppError, ErrorCode
from .models import CourseApplication

router = APIRouter(prefix='/api/v1', tags=['Данные заказчика'])
importer = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
viewer = require_roles(*ALL_ROLES)
Kind = Literal['vendors', 'learners', 'applications']


class ApplicationOut(BaseModel):
    id: int
    external_number: str
    course: str
    stream_number: str
    learner_id: int
    learner_name: str
    payment_status: str
    payment_status_label: str


def application_out(record):
    learner = record.learner
    return ApplicationOut(
        id=record.id, external_number=record.external_number, course=record.course,
        stream_number=record.stream_number, learner_id=record.learner_id,
        learner_name=' '.join(filter(None, [learner.last_name, learner.first_name, learner.middle_name])),
        payment_status=record.payment_status, payment_status_label='Не подтверждено данными',
    )


@router.get('/course-applications', response_model=list[ApplicationOut])
def list_applications(course: str | None = None, stream_number: str | None = None,
                      learner_id: int | None = None, auth: AuthContext = Depends(viewer), db: Session = Depends(get_db)):
    query = select(CourseApplication).options(selectinload(CourseApplication.learner)).order_by(CourseApplication.id.desc())
    if course:
        query = query.where(CourseApplication.course.ilike(like_pattern(course), escape='\\'))
    if stream_number:
        query = query.where(CourseApplication.stream_number == stream_number)
    if learner_id is not None:
        query = query.where(CourseApplication.learner_id == learner_id)
    return [application_out(item) for item in db.scalars(query.limit(100)).all()]


@router.get('/course-applications/{application_id}', response_model=ApplicationOut)
def get_application(application_id: int, auth: AuthContext = Depends(viewer), db: Session = Depends(get_db)):
    item = db.scalar(select(CourseApplication).options(selectinload(CourseApplication.learner)).where(CourseApplication.id == application_id))
    if item is None:
        raise not_found()
    return application_out(item)


@router.post('/customer-imports/{kind}/preview')
async def preview(kind: Kind, request: Request, file: UploadFile = File(...),
                  auth: AuthContext = Depends(importer), db: Session = Depends(get_db)):
    content = await file.read(10 * 1024 * 1024 + 1)
    rows = read_rows(kind, file.filename or '', content)
    report = CustomerImportRunner(db, request, apply=False).run(kind, rows)
    db.rollback()
    return report


@router.post('/customer-imports/{kind}/apply')
async def apply_import(kind: Kind, request: Request, file: UploadFile = File(...),
                       resolved_learner_ids: str = Form('{}'),
                       auth: AuthContext = Depends(importer), db: Session = Depends(get_db)):
    try:
        resolutions = json.loads(resolved_learner_ids)
        if not isinstance(resolutions, dict) or any(not str(row).isdigit() or not isinstance(learner_id, int) or learner_id <= 0
                                                     for row, learner_id in resolutions.items()):
            raise ValueError
    except (ValueError, json.JSONDecodeError) as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Некорректные решения по совпадениям слушателей') from error
    content = await file.read(10 * 1024 * 1024 + 1)
    rows = read_rows(kind, file.filename or '', content)
    report = CustomerImportRunner(db, request, apply=True, resolved_learner_ids=resolutions).run(kind, rows)
    # Do not retain the uploaded filename or rows; either can contain personal data.
    record_event(db, request, auth.user, f'customer_import.{kind}', summary='Применён импорт данных заказчика',
                 payload={'kind': kind, 'summary': report['summary']})
    db.commit()
    return report
