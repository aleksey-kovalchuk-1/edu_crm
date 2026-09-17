"""Mock LMS/website-CMS connector API (T-060, D-184-D-187). Contract: docs/api/integrations.md.

Authorization for a mock connector (no human session, no CSRF token) is a shared secret in
`X-Connector-Key` (D-186), checked against `settings.connector_api_key` -- never open by default (an
unset key rejects every call, it does not disable the check).
"""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_event
from .connectors import ConnectorValidationError, ResolvedInteraction, apply_interaction, find_link, outbound_state
from .db import get_db
from .errors import AppError, ErrorCode
from .models import IntegrationLink, Launch, University
from .workflows import active_statuses, default_template

router = APIRouter(prefix='/api/v1/integrations/{connector}', tags=['Интеграции (мок LMS/CMS)'])

Connector = Literal['lms', 'cms']
ExternalId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Name100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def require_connector_key(request: Request, x_connector_key: Annotated[str | None, Header()] = None):
    settings = request.app.state.settings
    if not settings.connector_api_key or x_connector_key != settings.connector_api_key:
        # Same response whether the key is missing, wrong, or the feature is unconfigured -- a wrong
        # guess must not learn anything about which case it hit.
        raise AppError(ErrorCode.UNAUTHENTICATED, 'Неверный или отсутствующий X-Connector-Key')
    return True


require_connector_key.authenticates = True

class InteractionIn(BaseModel):
    external_id: ExternalId
    correlation_id: str | None = Field(default=None, max_length=64)
    # Every field below is optional: absent means "unknown / do not change" on an update. A create still
    # needs university/program/product/responsible/deadline -- checked once the existing link is known,
    # so the message says "required to create", not "required" outright (see ConnectorValidationError).
    university: ShortText | None = None
    program: ShortText | None = None
    product: ShortText | None = None
    status: ShortText | None = None
    responsible: Name100 | None = None
    students: int | None = Field(default=None, ge=0, le=100000)
    deadline: date | None = None


class InteractionOut(BaseModel):
    crm_id: int
    external_id: str | None
    source: str
    action: str
    university: str | None
    program: str | None
    product: str | None
    workflow: str | None
    status: str | None
    responsible: str | None
    students: int | None
    deadline: date | None


def resolve_university(db, name):
    return db.scalar(select(University).where(University.name.ilike(name))) if name is not None else None


def resolve_status(db, template_id, name):
    if name is None:
        return None
    for status in active_statuses(db, template_id):
        if status.name.casefold() == name.casefold():
            return status
    return None


def field_error(code, field, message):
    return AppError(code, message, [{'field': field, 'message': message, 'type': 'value_error'}])


def to_out(connector, action, launch, link, db):
    state = outbound_state(db, launch, link)
    return InteractionOut(crm_id=launch.id, source=connector, action=action, external_id=state['external_id'], **{
        key: value for key, value in state.items() if key not in ('crm_id', 'external_id', 'updated_at')
    })


@router.post('/interactions', response_model=InteractionOut, status_code=200,
             summary='Входящее сообщение LMS/CMS: создать или обновить взаимодействие (идемпотентно)')
def inbound_interaction(connector: Connector, data: InteractionIn, request: Request, db: Session = Depends(get_db), _auth: bool = Depends(require_connector_key)):
    link = find_link(db, connector, data.external_id)
    status = None
    if link is None:
        university = resolve_university(db, data.university)
        if data.university is not None and university is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'university', f'Вуз «{data.university}» не найден')
        template_id = default_template(db).id
    else:
        university = None  # university is create-only; see app/connectors.py's ResolvedInteraction docstring
        template_id = db.get(Launch, link.launch_id).workflow_template_id
    if data.status is not None:
        status = resolve_status(db, template_id, data.status)
        if status is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'status', f'Статус «{data.status}» не найден среди активных статусов процесса')

    resolved = ResolvedInteraction(
        university=university, status=status, program=data.program, product=data.product,
        responsible=data.responsible, students=data.students, deadline=data.deadline,
    )
    try:
        launch, link, action = apply_interaction(db, connector, data.external_id, resolved)
    except ConnectorValidationError as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=list(error.problems)) from error

    record_event(
        db, request, None, f'integration.{connector}.inbound', entity_type='launch', entity_id=launch.id,
        summary=f'{connector.upper()}: взаимодействие #{launch.id} — {action}',
        payload={'source': connector, 'external_id': data.external_id, 'action': action, 'launch_id': launch.id},
        correlation_id=data.correlation_id,
    )
    db.commit()
    return to_out(connector, action, launch, link, db)


@router.get('/interactions', response_model=list[InteractionOut], summary='Исходящая выгрузка: текущее состояние взаимодействий')
def outbound_list(connector: Connector, after_id: int = 0, limit: int = 100, db: Session = Depends(get_db), _auth: bool = Depends(require_connector_key)):
    limit = max(1, min(limit, 500))
    launches = db.scalars(select(Launch).where(Launch.id > after_id).order_by(Launch.id).limit(limit)).all()
    links = {
        row.launch_id: row for row in db.scalars(
            select(IntegrationLink).where(IntegrationLink.source == connector, IntegrationLink.launch_id.in_([l.id for l in launches]))
        )
    } if launches else {}
    return [to_out(connector, 'current', launch, links.get(launch.id), db) for launch in launches]


@router.get('/interactions/{external_id}', response_model=InteractionOut, summary='Исходящая выгрузка: одно связанное взаимодействие')
def outbound_get(connector: Connector, external_id: ExternalId, db: Session = Depends(get_db), _auth: bool = Depends(require_connector_key)):
    link = find_link(db, connector, external_id)
    if link is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    launch = db.get(Launch, link.launch_id)
    return to_out(connector, 'current', launch, link, db)
