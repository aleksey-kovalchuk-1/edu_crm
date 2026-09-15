"""Workflow helpers shared by launch endpoints and seeding (docs/design/workflows.md)."""
from sqlalchemy import select

from .errors import AppError, ErrorCode
from .models import WorkflowStatus, WorkflowTemplate


def default_template(db):
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.is_default.is_(True)))
    if template is None:
        # Migration 0008 creates the default template; its absence means the database was not migrated.
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не настроен базовый процесс взаимодействия')
    return template


def active_statuses(db, template_id):
    return db.scalars(
        select(WorkflowStatus)
        .where(WorkflowStatus.template_id == template_id, WorkflowStatus.is_active.is_(True))
        .order_by(WorkflowStatus.position)
    ).all()


def status_at_position(db, template_id, position):
    return db.scalar(select(WorkflowStatus).where(
        WorkflowStatus.template_id == template_id, WorkflowStatus.position == position, WorkflowStatus.is_active.is_(True),
    ))
