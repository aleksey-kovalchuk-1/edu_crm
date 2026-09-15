"""Workflow helpers shared by launch endpoints, workflow routes and seeding (docs/design/workflows.md)."""
from sqlalchemy import select

from .catalog_routes import university_scope
from .errors import AppError, ErrorCode
from .models import Launch, WorkflowStatus, WorkflowTemplate


def default_template(db):
    template = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.is_default.is_(True)))
    if template is None:
        # Migration 0008 creates the default template; its absence means the database was not migrated.
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не настроен базовый процесс взаимодействия')
    return template


def all_statuses(db, template_id):
    return db.scalars(select(WorkflowStatus).where(WorkflowStatus.template_id == template_id).order_by(WorkflowStatus.position)).all()


def active_statuses(db, template_id):
    return [status for status in all_statuses(db, template_id) if status.is_active]


def status_at_position(db, template_id, position):
    return db.scalar(select(WorkflowStatus).where(
        WorkflowStatus.template_id == template_id, WorkflowStatus.position == position, WorkflowStatus.is_active.is_(True),
    ))


def launch_in_scope(db, user, launch_id, *, lock=False):
    # Launches belong to a university, so a manager only reaches launches of universities assigned to them (D-141).
    query = select(Launch).where(Launch.id == launch_id, university_scope(Launch.university_id, user))
    if lock:
        query = query.with_for_update(of=Launch)
    launch = db.scalar(query)
    if launch is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    return launch
