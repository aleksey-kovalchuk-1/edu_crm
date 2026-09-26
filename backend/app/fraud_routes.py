"""Restricted human review of safe antifraud signals."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import not_found
from .db import get_db
from .errors import AppError, ErrorCode
from .models import FraudAlert, utcnow

router = APIRouter(prefix='/api/v1/fraud-alerts', tags=['Проверка сигналов'])
reviewer = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
Status = Literal['open', 'in_review', 'cleared', 'confirmed']
Priority = Literal['low', 'medium', 'high']
Resolution = Literal['legitimate_shared_contact', 'data_corrected', 'false_positive',
                     'confirmed_by_review', 'needs_more_information']


class ReviewIn(BaseModel):
    status: Status
    resolution_code: Resolution | None = None
    expected_updated_at: datetime


def alert_out(alert):
    return {'id': alert.id, 'rule_code': alert.rule_code, 'rule_version': alert.rule_version,
            'evidence_kind': alert.evidence_kind, 'priority': alert.priority, 'status': alert.status,
            'entity_type': alert.entity_type, 'entity_id': alert.entity_id,
            'related_entity_id': alert.related_entity_id, 'batch_id': alert.batch_id,
            'row_number': alert.row_number, 'created_at': alert.created_at,
            'updated_at': alert.updated_at, 'reviewed_by_user_id': alert.reviewed_by_user_id,
            'reviewed_at': alert.reviewed_at, 'resolution_code': alert.resolution_code}


@router.get('/status')
def fraud_status(request: Request, auth: AuthContext = Depends(reviewer)):
    settings = request.app.state.settings
    state = ('disabled_no_key' if not settings.fraud_match_key else
             'active' if settings.fraud_match_coverage_complete else 'needs_backfill')
    return {'document_match': state, 'rule_version': 1,
            'batch_row_limit': settings.fraud_batch_row_limit,
            'hourly_import_limit': settings.fraud_hourly_import_limit}


@router.get('')
def list_alerts(status: Status | None = None, priority: Priority | None = None,
                limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                auth: AuthContext = Depends(reviewer), db: Session = Depends(get_db)):
    query = select(FraudAlert)
    if status:
        query = query.where(FraudAlert.status == status)
    if priority:
        query = query.where(FraudAlert.priority == priority)
    query = query.order_by(FraudAlert.created_at.desc(), FraudAlert.id.desc()).limit(limit).offset(offset)
    return [alert_out(alert) for alert in db.scalars(query).all()]


@router.get('/{alert_id}')
def get_alert(alert_id: int, auth: AuthContext = Depends(reviewer), db: Session = Depends(get_db)):
    alert = db.get(FraudAlert, alert_id)
    if alert is None:
        raise not_found()
    return alert_out(alert)


@router.patch('/{alert_id}')
def review_alert(alert_id: int, data: ReviewIn, request: Request,
                 auth: AuthContext = Depends(reviewer), db: Session = Depends(get_db)):
    alert = db.get(FraudAlert, alert_id)
    if alert is None:
        raise not_found()
    if alert.updated_at != data.expected_updated_at:
        raise AppError(ErrorCode.CONFLICT, 'Сигнал уже изменён другим проверяющим')
    if data.status in {'cleared', 'confirmed'} and data.resolution_code is None:
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Выберите причину решения')
    allowed = {
        'open': {'in_review', 'cleared', 'confirmed'},
        'in_review': {'open', 'cleared', 'confirmed'},
        'cleared': {'in_review'},
        'confirmed': {'in_review'},
    }
    if data.status not in allowed[alert.status]:
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Недопустимый переход статуса')
    updated = utcnow()
    result = db.execute(update(FraudAlert).where(FraudAlert.id == alert_id,
                                                 FraudAlert.updated_at == data.expected_updated_at)
                        .values(status=data.status, resolution_code=data.resolution_code,
                                reviewed_by_user_id=auth.user.id, reviewed_at=updated,
                                updated_at=updated).returning(FraudAlert.id)).scalar_one_or_none()
    if result is None:
        raise AppError(ErrorCode.CONFLICT, 'Сигнал уже изменён другим проверяющим')
    record_event(db, request, auth.user, 'fraud_alert.review', entity_type='fraud_alert', entity_id=alert_id,
                 summary='Решение по сигналу проверки',
                 payload={'rule_code': alert.rule_code, 'status': data.status,
                          'resolution_code': data.resolution_code})
    db.commit()
    db.refresh(alert)
    return alert_out(alert)
