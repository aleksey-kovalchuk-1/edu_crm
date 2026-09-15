from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .db import get_db
from .models import AuditEvent, User

router = APIRouter(prefix='/api/v1/audit', tags=['Журнал действий'])
SEE_EVERYONE_ROLES = frozenset({ROLE_SUPERVISOR, ROLE_ADMIN})


class AuditActor(BaseModel):
    id: int
    full_name: str


class AuditEventOut(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str
    user: AuditActor | None


@router.get('/recent', response_model=list[AuditEventOut], summary='Последние действия пользователей')
def recent_events(
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_roles(*ALL_ROLES)),
    db: Session = Depends(get_db),
):
    query = (
        select(AuditEvent, User)
        .outerjoin(User, User.id == AuditEvent.user_id)
        .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    # Managers see their own history; heads and administrators see everyone's (D-131).
    if SEE_EVERYONE_ROLES.isdisjoint(auth.user.roles):
        query = query.where(AuditEvent.user_id == auth.user.id)
    return [
        AuditEventOut(
            id=event.id,
            occurred_at=event.occurred_at,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            summary=event.summary,
            user=AuditActor(id=user.id, full_name=user.full_name) if user is not None else None,
        )
        for event, user in db.execute(query)
    ]
