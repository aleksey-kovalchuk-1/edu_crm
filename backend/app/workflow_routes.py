"""Workflow templates, status changes and attachments (design: docs/design/workflows.md; decisions D-149–D-154).

Comments may contain personal data, so audit events record only that a comment exists, never its text.
"""
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import PersonOut, university_scope
from .db import get_db
from .errors import AppError, ErrorCode
from .models import Attachment, Launch, StageEvent, StatusChange, User, WorkflowStatus, WorkflowTemplate
from .uploads import ALLOWED_TYPES_TEXT, MAX_ATTACHMENTS, field_error, store_upload
from .workflows import all_statuses, launch_in_scope

router = APIRouter(prefix='/api/v1', tags=['Процессы и статусы'])
any_role = require_roles(*ALL_ROLES)
workflow_editor = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)

MAX_COMMENT_LENGTH = 2000
MAX_STATUSES = 50

StatusName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TemplateName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


# ---------- schemas ----------

class StatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    position: int
    is_final: bool
    is_active: bool


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    is_default: bool
    is_active: bool
    statuses: list[StatusOut]


class WorkflowIn(BaseModel):
    name: TemplateName
    description: Description = ''
    statuses: list[StatusName] = Field(min_length=1, max_length=MAX_STATUSES)

    @field_validator('statuses')
    @classmethod
    def unique_names(cls, names):
        if len(set(names)) != len(names):
            raise ValueError('Названия статусов в процессе не должны повторяться')
        return names


class WorkflowPatch(BaseModel):
    name: TemplateName | None = None
    description: Description | None = None
    is_active: bool | None = None


class StatusIn(BaseModel):
    name: StatusName
    is_final: bool = False


class StatusPatch(BaseModel):
    name: StatusName | None = None
    is_final: bool | None = None
    is_active: bool | None = None


class StatusOrderIn(BaseModel):
    status_ids: list[int] = Field(min_length=1, max_length=MAX_STATUSES)


class StatusRef(BaseModel):
    id: int
    name: str


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class StatusChangeOut(BaseModel):
    id: int
    launch_id: int
    from_status: StatusRef | None
    to_status: StatusRef
    comment: str
    author: PersonOut | None
    created_at: datetime
    attachments: list[AttachmentOut]


# ---------- helpers ----------

def flush_or_conflict(db, field, message):
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise field_error(ErrorCode.CONFLICT, field, message) from error


def load_template(db, template_id, *, lock=False):
    query = select(WorkflowTemplate).where(WorkflowTemplate.id == template_id)
    if lock:
        query = query.with_for_update()
    template = db.scalar(query)
    if template is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    return template


def workflow_out(db, template):
    return WorkflowOut(
        id=template.id, name=template.name, description=template.description, is_default=template.is_default,
        is_active=template.is_active, statuses=[StatusOut.model_validate(s) for s in all_statuses(db, template.id)],
    )


def changed_fields(record, data):
    return {name: {'from': getattr(record, name), 'to': value}
            for name, value in data.model_dump(exclude_none=True).items() if getattr(record, name) != value}




def status_change_outs(db, changes):
    status_ids = {c.to_status_id for c in changes} | {c.from_status_id for c in changes if c.from_status_id}
    statuses = {s.id: s for s in db.scalars(select(WorkflowStatus).where(WorkflowStatus.id.in_(status_ids)))} if status_ids else {}
    user_ids = {c.user_id for c in changes if c.user_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}

    def ref(status_id):
        return StatusRef(id=status_id, name=statuses[status_id].name) if status_id in statuses else None

    return [
        StatusChangeOut(
            id=c.id, launch_id=c.launch_id, from_status=ref(c.from_status_id), to_status=ref(c.to_status_id), comment=c.comment,
            author=PersonOut(id=users[c.user_id].id, full_name=users[c.user_id].full_name) if c.user_id in users else None,
            created_at=c.created_at, attachments=[AttachmentOut.model_validate(a) for a in c.attachments],
        )
        for c in changes
    ]


# ---------- templates ----------

@router.get('/workflows', response_model=list[WorkflowOut], summary='Процессы и их статусы', dependencies=[Depends(any_role)])
def list_workflows(db: Session = Depends(get_db)):
    templates = db.scalars(select(WorkflowTemplate).order_by(WorkflowTemplate.is_default.desc(), WorkflowTemplate.name)).all()
    return [workflow_out(db, template) for template in templates]


@router.post('/workflows', response_model=WorkflowOut, status_code=201, summary='Создать процесс')
def create_workflow(data: WorkflowIn, request: Request, auth: AuthContext = Depends(workflow_editor), db: Session = Depends(get_db)):
    template = WorkflowTemplate(name=data.name, description=data.description)
    db.add(template)
    flush_or_conflict(db, 'name', 'Процесс с таким названием уже есть')
    for position, name in enumerate(data.statuses):
        db.add(WorkflowStatus(template_id=template.id, name=name, position=position, is_final=position == len(data.statuses) - 1))
    record_event(db, request, auth.user, 'workflow.create', entity_type='workflow', entity_id=template.id,
                 summary=f'Создан процесс «{template.name}» ({len(data.statuses)} статусов)',
                 payload={'name': data.name, 'statuses': data.statuses})
    db.commit()
    return workflow_out(db, template)


@router.patch('/workflows/{workflow_id}', response_model=WorkflowOut, summary='Изменить процесс')
def update_workflow(workflow_id: int, data: WorkflowPatch, request: Request, auth: AuthContext = Depends(workflow_editor), db: Session = Depends(get_db)):
    template = load_template(db, workflow_id, lock=True)
    changes = changed_fields(template, data)
    if changes.get('is_active', {}).get('to') is False and template.is_default:
        raise field_error(ErrorCode.CONFLICT, 'is_active', 'Базовый процесс нельзя отключить')
    if changes:
        for name, change in changes.items():
            setattr(template, name, change['to'])
        flush_or_conflict(db, 'name', 'Процесс с таким названием уже есть')
        record_event(db, request, auth.user, 'workflow.update', entity_type='workflow', entity_id=template.id,
                     summary=f'Изменён процесс «{template.name}»', payload=changes)
        db.commit()
    return workflow_out(db, template)


@router.post('/workflows/{workflow_id}/statuses', response_model=StatusOut, status_code=201, summary='Добавить статус')
def add_status(workflow_id: int, data: StatusIn, request: Request, auth: AuthContext = Depends(workflow_editor), db: Session = Depends(get_db)):
    template = load_template(db, workflow_id, lock=True)  # the lock keeps positions unique under concurrent additions
    count = db.scalar(select(func.count()).select_from(WorkflowStatus).where(WorkflowStatus.template_id == template.id))
    if count >= MAX_STATUSES:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'name', f'В процессе не может быть больше {MAX_STATUSES} статусов')
    status = WorkflowStatus(template_id=template.id, name=data.name, position=count, is_final=data.is_final)
    db.add(status)
    flush_or_conflict(db, 'name', 'Статус с таким названием в процессе уже есть')
    record_event(db, request, auth.user, 'workflow_status.create', entity_type='workflow', entity_id=template.id,
                 summary=f'В процесс «{template.name}» добавлен статус «{status.name}»', payload=data.model_dump())
    db.commit()
    return status


@router.patch('/workflow-statuses/{status_id}', response_model=StatusOut, summary='Переименовать или отключить статус')
def update_status(status_id: int, data: StatusPatch, request: Request, auth: AuthContext = Depends(workflow_editor), db: Session = Depends(get_db)):
    status = db.scalar(select(WorkflowStatus).where(WorkflowStatus.id == status_id))
    if status is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    template = load_template(db, status.template_id, lock=True)
    changes = changed_fields(status, data)
    if changes.get('is_active', {}).get('to') is False:
        in_use = db.scalar(select(func.count()).select_from(Launch).where(Launch.status_id == status.id))
        if in_use:
            raise field_error(ErrorCode.CONFLICT, 'is_active', f'Статус нельзя отключить: в нём {in_use} взаимодействий')
        others = db.scalar(select(func.count()).select_from(WorkflowStatus).where(
            WorkflowStatus.template_id == template.id, WorkflowStatus.id != status.id, WorkflowStatus.is_active.is_(True)))
        if not others:
            raise field_error(ErrorCode.CONFLICT, 'is_active', 'В процессе должен остаться хотя бы один активный статус')
    if changes:
        old_name = status.name
        for name, change in changes.items():
            setattr(status, name, change['to'])
        flush_or_conflict(db, 'name', 'Статус с таким названием в процессе уже есть')
        record_event(db, request, auth.user, 'workflow_status.update', entity_type='workflow', entity_id=template.id,
                     summary=f'Процесс «{template.name}»: изменён статус «{old_name}»', payload=changes)
        db.commit()
    return status


@router.put('/workflows/{workflow_id}/status-order', response_model=WorkflowOut, summary='Изменить порядок статусов')
def reorder_statuses(workflow_id: int, data: StatusOrderIn, request: Request, auth: AuthContext = Depends(workflow_editor), db: Session = Depends(get_db)):
    template = load_template(db, workflow_id, lock=True)
    statuses = {status.id: status for status in all_statuses(db, template.id)}
    if len(data.status_ids) != len(statuses) or set(data.status_ids) != set(statuses):
        raise field_error(ErrorCode.VALIDATION_ERROR, 'status_ids', 'Перечислите все статусы процесса ровно по одному разу')
    moved = {status_id: position for position, status_id in enumerate(data.status_ids) if statuses[status_id].position != position}
    if moved:
        for status_id, position in moved.items():
            statuses[status_id].position = position
            # launches.stage mirrors the status position for the older stage endpoints (D-149).
            db.execute(update(Launch).where(Launch.status_id == status_id).values(stage=position))
        record_event(db, request, auth.user, 'workflow.reorder', entity_type='workflow', entity_id=template.id,
                     summary=f'Изменён порядок статусов процесса «{template.name}»', payload={'status_ids': data.status_ids})
        db.commit()
    return workflow_out(db, template)


# ---------- status changes and files ----------

@router.get('/launches/{launch_id}/status-changes', response_model=list[StatusChangeOut], summary='История статусов с комментариями и файлами')
def list_status_changes(launch_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    launch_in_scope(db, auth.user, launch_id)
    changes = db.scalars(
        select(StatusChange).where(StatusChange.launch_id == launch_id)
        .options(selectinload(StatusChange.attachments)).order_by(StatusChange.created_at.desc(), StatusChange.id.desc())
    ).all()
    return status_change_outs(db, changes)


@router.post('/launches/{launch_id}/status-changes', response_model=StatusChangeOut, status_code=201,
             summary='Сменить статус с комментарием и файлами',
             description=f'`multipart/form-data`. Не больше {MAX_ATTACHMENTS} файлов по 20 МБ; форматы: {ALLOWED_TYPES_TEXT}. '
                         'Тот же статус можно указать, только если добавлен комментарий или файл.')
def change_status(
    launch_id: int,
    request: Request,
    status_id: Annotated[int, Form()],
    comment: Annotated[str, Form()] = '',
    files: Annotated[list[UploadFile] | None, File()] = None,
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    launch = launch_in_scope(db, auth.user, launch_id, lock=True)
    comment = comment.strip()
    if len(comment) > MAX_COMMENT_LENGTH:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'comment', f'Комментарий длиннее {MAX_COMMENT_LENGTH} символов')
    uploads = [upload for upload in files or [] if upload.filename]  # browsers send an empty part when no file is chosen
    if len(uploads) > MAX_ATTACHMENTS:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'files', f'Не больше {MAX_ATTACHMENTS} файлов за одну смену статуса')
    status = db.scalar(select(WorkflowStatus).where(WorkflowStatus.id == status_id, WorkflowStatus.template_id == launch.workflow_template_id))
    if status is None or not status.is_active:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'status_id', 'Этот статус недоступен для взаимодействия')
    same_status = status.id == launch.status_id
    if same_status and not comment and not uploads:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'status_id', 'Взаимодействие уже в этом статусе: добавьте комментарий или файл')
    previous = db.get(WorkflowStatus, launch.status_id)

    directory = Path(request.app.state.settings.attachments_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stored = []
    try:
        change = StatusChange(launch_id=launch.id, from_status_id=launch.status_id, to_status_id=status.id, comment=comment, user_id=auth.user.id)
        db.add(change)
        db.flush()
        for upload in uploads:
            filename, content_type, size, sha256, key, path = store_upload(upload, directory)
            stored.append(path)
            db.add(Attachment(
                filename=filename, content_type=content_type, size_bytes=size, sha256=sha256, storage_key=key,
                status_change_id=change.id, launch_id=launch.id, uploaded_by_user_id=auth.user.id,
            ))
        if not same_status:
            launch.status_id = status.id
            launch.stage = status.position
            db.add(StageEvent(launch_id=launch.id, stage=status.position))
        summary = (f'«{launch.program}»: к статусу «{status.name}» добавлены комментарий или файлы' if same_status
                   else f'«{launch.program}»: статус «{previous.name}» → «{status.name}»')
        record_event(db, request, auth.user, 'launch.status_change', entity_type='launch', entity_id=launch.id, summary=summary,
                     payload={'from_status_id': previous.id, 'to_status_id': status.id, 'has_comment': bool(comment), 'attachments': len(uploads)})
        db.commit()
    except BaseException:
        db.rollback()
        for path in stored:
            path.unlink(missing_ok=True)
        raise
    change = db.scalar(select(StatusChange).where(StatusChange.id == change.id).options(selectinload(StatusChange.attachments)))
    return status_change_outs(db, [change])[0]


@router.get('/attachments/{attachment_id}', response_class=FileResponse, summary='Скачать файл',
            responses={200: {'content': {'application/octet-stream': {}}}})
def download_attachment(attachment_id: int, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    attachment = db.scalar(
        select(Attachment).join(Launch, Launch.id == Attachment.launch_id)
        .where(Attachment.id == attachment_id, university_scope(Launch.university_id, auth.user))
    )
    if attachment is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    path = Path(request.app.state.settings.attachments_dir) / attachment.storage_key
    if not path.is_file():
        raise AppError(ErrorCode.RECORD_NOT_FOUND, 'Файл не найден в хранилище')
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.filename,
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})
