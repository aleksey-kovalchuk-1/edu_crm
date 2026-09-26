"""Preview/apply customer imports and read-only course application cards."""
import json
from dataclasses import asdict
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import like_pattern, not_found
from .customer_imports import CustomerImportRunner, read_customer_file
from .db import get_db
from .errors import AppError, ErrorCode
from .fraud_alerts import upsert_alert
from .fraud_rules import FraudSignal, evaluate_import_velocity
from .models import CourseApplication, CustomerImportBatch, CustomerImportRowLink, utcnow

router = APIRouter(prefix='/api/v1', tags=['Данные заказчика'])
importer = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
viewer = require_roles(*ALL_ROLES)
Kind = Literal['vendors', 'learners', 'applications']


def velocity_signals(db, request, user_id, rows):
    recent = db.scalar(select(func.count()).select_from(CustomerImportBatch).where(
        CustomerImportBatch.created_by_user_id == user_id,
        CustomerImportBatch.created_at >= utcnow() - timedelta(hours=1))) or 0
    settings = request.app.state.settings
    return evaluate_import_velocity(rows, recent + 1, settings.fraud_batch_row_limit,
                                    settings.fraud_hourly_import_limit)


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
                  mapping: str | None = Form(None),
                  auth: AuthContext = Depends(importer), db: Session = Depends(get_db)):
    content = await file.read(10 * 1024 * 1024 + 1)
    parsed = read_customer_file(kind, file.filename or '', content, selected_mapping=parse_mapping(mapping))
    report = CustomerImportRunner(db, request, apply=False).run(kind, parsed.rows)
    batch_signals = velocity_signals(db, request, auth.user.id, len(parsed.rows))
    db.rollback()
    return {**report, 'template_version': parsed.template_version,
            'mapping': parsed.mapping, 'unmapped_headers': parsed.unmapped_headers,
            'batch_signals': [asdict(signal) for signal in batch_signals]}


def parse_mapping(value):
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, json.JSONDecodeError) as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Некорректное сопоставление столбцов') from error
    if not isinstance(parsed, dict):
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Некорректное сопоставление столбцов')
    return parsed


def batch_out(batch):
    return {'id': batch.id, 'kind': batch.kind, 'template_version': batch.template_version,
            'created_by_user_id': batch.created_by_user_id, 'created_at': batch.created_at,
            'summary': {field: getattr(batch, field) for field in
                        ('rows', 'valid', 'invalid', 'skipped', 'created', 'updated')}}


@router.get('/customer-imports/history')
def import_history(auth: AuthContext = Depends(importer), db: Session = Depends(get_db)):
    batches = db.scalars(select(CustomerImportBatch).order_by(CustomerImportBatch.id.desc()).limit(100)).all()
    return [batch_out(batch) for batch in batches]


@router.get('/customer-imports/history/{batch_id}')
def import_history_detail(batch_id: int, auth: AuthContext = Depends(importer), db: Session = Depends(get_db)):
    batch = db.scalar(select(CustomerImportBatch).options(selectinload(CustomerImportBatch.record_links)).where(CustomerImportBatch.id == batch_id))
    if batch is None:
        raise not_found()
    return {**batch_out(batch), 'record_links': [
        {'row_number': link.row_number, 'entity_type': link.entity_type,
         'entity_id': link.entity_id, 'action': link.action} for link in batch.record_links]}


@router.post('/customer-imports/{kind}/apply')
async def apply_import(kind: Kind, request: Request, file: UploadFile = File(...),
                       resolved_learner_ids: str = Form('{}'),
                       mapping: str | None = Form(None),
                       auth: AuthContext = Depends(importer), db: Session = Depends(get_db)):
    try:
        resolutions = json.loads(resolved_learner_ids)
        if not isinstance(resolutions, dict) or any(not str(row).isdigit() or not isinstance(learner_id, int) or learner_id <= 0
                                                     for row, learner_id in resolutions.items()):
            raise ValueError
    except (ValueError, json.JSONDecodeError) as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Некорректные решения по совпадениям слушателей') from error
    content = await file.read(10 * 1024 * 1024 + 1)
    parsed = read_customer_file(kind, file.filename or '', content, selected_mapping=parse_mapping(mapping))
    if not parsed.rows:
        raise AppError(ErrorCode.VALIDATION_ERROR, 'В файле нет строк для применения')
    report = CustomerImportRunner(db, request, apply=True, resolved_learner_ids=resolutions).run(kind, parsed.rows)
    batch_signals = velocity_signals(db, request, auth.user.id, len(parsed.rows))
    batch = CustomerImportBatch(kind=kind, template_version=parsed.template_version,
                                created_by_user_id=auth.user.id, **report['summary'])
    db.add(batch)
    db.flush()
    for link in report['record_links']:
        db.add(CustomerImportRowLink(batch_id=batch.id, **link))
    for row in report['rows']:
        for safe_signal in row['signals']:
            upsert_alert(db, FraudSignal(**safe_signal), batch.id)
    for signal in batch_signals:
        upsert_alert(db, signal, batch.id)
    # Do not retain the uploaded filename or rows; either can contain personal data.
    record_event(db, request, auth.user, f'customer_import.{kind}', summary='Применён импорт данных заказчика',
                 payload={'kind': kind, 'summary': report['summary'],
                          'resolved_learner_ids': resolutions})
    db.commit()
    return {**report, 'batch_id': batch.id, 'template_version': parsed.template_version,
            'mapping': parsed.mapping, 'unmapped_headers': parsed.unmapped_headers,
            'batch_signals': [asdict(signal) for signal in batch_signals]}
