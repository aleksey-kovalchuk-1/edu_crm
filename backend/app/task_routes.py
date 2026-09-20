"""Tasks workspace API (docs/design/tasks.md): task CRUD, status workflow, checklists, subtasks,
comments/activity, filters/counters/Deadline view, configurable columns and bulk actions.

Plan templates are a later slice, not this file yet.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from .audit import record_event
from .auth import ALL_ROLES, AuthContext, require_roles
from .catalog_routes import PersonOut, like_pattern, not_found, sees_all, university_in_scope
from .db import get_db
from .errors import AppError, ErrorCode
from .models import (
    Contract, Launch, Task, TaskAttachment, TaskChecklistItem, TaskComment, TaskEvent, TaskMember,
    TaskUserPreferences, University, User, utcnow,
)
from .task_policy import TaskAction, can, visible_tasks_query
from .uploads import ALLOWED_TYPES_TEXT, MAX_ATTACHMENTS, store_upload

router = APIRouter(prefix='/api/v1', tags=['Задачи'])
any_role = require_roles(*ALL_ROLES)

MAX_PAGE_SIZE = 100
MAX_COMMENT_LENGTH = 2000
MEMBER_FIELD_ROLE = {'assignee_ids': 'assignee', 'participant_ids': 'participant', 'observer_ids': 'observer'}
SORT_COLUMNS = {'deadline': Task.deadline, 'created_at': Task.created_at, 'priority': Task.priority, 'title': Task.title, 'status': Task.status}
SCOPE_MEMBER_ROLE = {'assigned': 'assignee', 'participating': 'participant', 'observing': 'observer'}

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
Priority = Literal['low', 'normal', 'high', 'urgent']
Scope = Literal['mine', 'assigned', 'created', 'participating', 'observing', 'team', 'all']
TaskStatus = Literal['new', 'in_progress', 'awaiting_review', 'completed', 'deferred', 'cancelled']

STATUS_LABELS = {
    'new': 'Новая', 'in_progress': 'В работе', 'awaiting_review': 'На проверке',
    'completed': 'Завершена', 'deferred': 'Отложена', 'cancelled': 'Отменена',
}

# (from, to) -> who may act: 'assignee' (creator, assignee or manager) or 'manager' (creator or manager).
# A manager is a supervisor/admin (sees_all) or the task's own creator.
TRANSITIONS = {
    ('new', 'in_progress'): 'assignee',
    ('new', 'deferred'): 'assignee',
    ('new', 'cancelled'): 'manager',
    ('in_progress', 'awaiting_review'): 'assignee',
    ('in_progress', 'completed'): 'assignee',
    ('in_progress', 'deferred'): 'assignee',
    ('in_progress', 'cancelled'): 'manager',
    ('deferred', 'in_progress'): 'assignee',
    ('deferred', 'cancelled'): 'manager',
    ('awaiting_review', 'completed'): 'manager',
    ('awaiting_review', 'in_progress'): 'manager',
    ('completed', 'in_progress'): 'manager',
}


def field_error(code, field, message):
    return AppError(code, message, [{'field': field, 'message': message, 'type': 'value_error'}])


# ---------- schemas ----------

class UniversityRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class LaunchRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    program: str


class ContractRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    contract_number: str


class MembersIn(BaseModel):
    assignee_ids: list[int] = Field(default_factory=list, max_length=50)
    participant_ids: list[int] = Field(default_factory=list, max_length=50)
    observer_ids: list[int] = Field(default_factory=list, max_length=50)


class TaskCreate(MembersIn):
    title: Title
    description: Description = ''
    deadline: date | None = None
    planned_start: date | None = None
    priority: Priority = 'normal'
    university_id: int | None = Field(default=None, gt=0)
    launch_id: int | None = Field(default=None, gt=0)
    contract_id: int | None = Field(default=None, gt=0)
    approval_required: bool = False
    require_checklist_complete: bool = True
    # Only a supervisor/admin may set this to someone other than themselves (checked in the route).
    creator_id: int | None = Field(default=None, gt=0)
    # A subtask is a normal task with this set; only one level deep (the parent must not itself be a subtask).
    parent_task_id: int | None = Field(default=None, gt=0)


class TaskPatch(BaseModel):
    version: int
    title: Title | None = None
    description: Description | None = None
    deadline: date | None = None
    planned_start: date | None = None
    priority: Priority | None = None
    approval_required: bool | None = None


class ChecklistItemOut(BaseModel):
    id: int
    title: str
    position: int
    is_done: bool
    assignee: PersonOut | None
    deadline: date | None
    completed_by: PersonOut | None
    completed_at: datetime | None


class TaskRef(BaseModel):
    id: int
    title: str
    status: str


class SubtaskSummary(BaseModel):
    total: int
    completed: int


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str
    deadline: date | None
    planned_start: date | None
    creator: PersonOut | None
    university: UniversityRef | None
    interaction: LaunchRef | None
    contract: ContractRef | None
    assignees: list[PersonOut]
    participants: list[PersonOut]
    observers: list[PersonOut]
    approval_required: bool
    require_checklist_complete: bool
    checklist: list[ChecklistItemOut]
    parent: TaskRef | None
    subtasks: SubtaskSummary
    created_at: datetime
    updated_at: datetime
    version: int


class TaskListItemOut(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    deadline: date | None
    creator: PersonOut | None
    assignees: list[PersonOut]
    university: UniversityRef | None
    created_at: datetime
    version: int


class TaskPage(BaseModel):
    items: list[TaskListItemOut]
    total: int
    limit: int
    offset: int


# ---------- helpers ----------

def load_members(db, data):
    """{role: [User, ...]} for the three member-id lists in `data`; rejects unknown/inactive ids."""
    result = {}
    for field, role in MEMBER_FIELD_ROLE.items():
        ids = sorted(set(getattr(data, field)))
        users = db.scalars(select(User).where(User.id.in_(ids), User.is_active.is_(True))).all() if ids else []
        if len(users) != len(ids):
            raise field_error(ErrorCode.VALIDATION_ERROR, field, 'Один или несколько пользователей не найдены или неактивны')
        result[role] = users
    return result


def resolve_links(db, data):
    """Validates/derives the university a task belongs to from its interaction and contract links."""
    launch = None
    contract = None
    university_id = data.university_id
    if data.launch_id is not None:
        launch = db.get(Launch, data.launch_id)
        if launch is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'launch_id', 'Взаимодействие не найдено')
        if university_id is None:
            university_id = launch.university_id
        elif launch.university_id != university_id:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'launch_id', 'Взаимодействие относится к другому учебному заведению')
    if data.contract_id is not None:
        contract = db.get(Contract, data.contract_id)
        if contract is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'contract_id', 'Договор не найден')
        if university_id is None:
            university_id = contract.university_id
        elif contract.university_id != university_id:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'contract_id', 'Договор относится к другому учебному заведению')
    return university_id, launch, contract


def task_out(db, task_id):
    task = db.scalar(
        select(Task).where(Task.id == task_id)
        .options(selectinload(Task.members), selectinload(Task.checklist_items))
    )
    refs = {
        'creator': db.get(User, task.creator_id) if task.creator_id else None,
        'university': db.get(University, task.university_id) if task.university_id else None,
        'launch': db.get(Launch, task.launch_id) if task.launch_id else None,
        'contract': db.get(Contract, task.contract_id) if task.contract_id else None,
        'parent': db.get(Task, task.parent_task_id) if task.parent_task_id else None,
    }
    member_user_ids = {m.user_id for m in task.members}
    checklist_user_ids = {i.assignee_user_id for i in task.checklist_items if i.assignee_user_id}
    checklist_user_ids |= {i.completed_by_user_id for i in task.checklist_items if i.completed_by_user_id}
    users_by_id = {
        u.id: u for u in db.scalars(select(User).where(User.id.in_(member_user_ids | checklist_user_ids)))
    } if (member_user_ids or checklist_user_ids) else {}

    def by_role(role):
        return [PersonOut.model_validate(users_by_id[m.user_id]) for m in task.members if m.role == role and m.user_id in users_by_id]

    def user_ref(user_id):
        return PersonOut.model_validate(users_by_id[user_id]) if user_id in users_by_id else None

    subtask_rows = db.execute(select(Task.status).where(Task.parent_task_id == task.id)).scalars().all()

    return TaskOut(
        id=task.id, title=task.title, description=task.description, status=task.status, priority=task.priority,
        deadline=task.deadline, planned_start=task.planned_start,
        creator=PersonOut.model_validate(refs['creator']) if refs['creator'] else None,
        university=UniversityRef.model_validate(refs['university']) if refs['university'] else None,
        interaction=LaunchRef.model_validate(refs['launch']) if refs['launch'] else None,
        contract=ContractRef.model_validate(refs['contract']) if refs['contract'] else None,
        assignees=by_role('assignee'), participants=by_role('participant'), observers=by_role('observer'),
        approval_required=task.approval_required, require_checklist_complete=task.require_checklist_complete,
        checklist=[
            ChecklistItemOut(
                id=i.id, title=i.title, position=i.position, is_done=i.is_done,
                assignee=user_ref(i.assignee_user_id), deadline=i.deadline,
                completed_by=user_ref(i.completed_by_user_id), completed_at=i.completed_at,
            )
            for i in sorted(task.checklist_items, key=lambda i: i.position)
        ],
        parent=TaskRef(id=refs['parent'].id, title=refs['parent'].title, status=refs['parent'].status) if refs['parent'] else None,
        subtasks=SubtaskSummary(total=len(subtask_rows), completed=sum(1 for s in subtask_rows if s == 'completed')),
        created_at=task.created_at, updated_at=task.updated_at, version=task.version,
    )


def task_list_items(db, tasks):
    """Batch-loads creators/assignees/universities for a page of tasks instead of querying per row."""
    task_ids = [t.id for t in tasks]
    creator_ids = {t.creator_id for t in tasks if t.creator_id}
    university_ids = {t.university_id for t in tasks if t.university_id}
    members = db.execute(
        select(TaskMember.task_id, TaskMember.user_id).where(TaskMember.task_id.in_(task_ids), TaskMember.role == 'assignee')
    ).all() if task_ids else []
    member_user_ids = {m.user_id for m in members}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(creator_ids | member_user_ids)))} if (creator_ids or member_user_ids) else {}
    universities = {u.id: u for u in db.scalars(select(University).where(University.id.in_(university_ids)))} if university_ids else {}
    assignees_by_task = {}
    for task_id, user_id in members:
        assignees_by_task.setdefault(task_id, []).append(user_id)

    return [
        TaskListItemOut(
            id=t.id, title=t.title, status=t.status, priority=t.priority, deadline=t.deadline,
            creator=PersonOut.model_validate(users[t.creator_id]) if t.creator_id in users else None,
            assignees=[PersonOut.model_validate(users[uid]) for uid in assignees_by_task.get(t.id, []) if uid in users],
            university=UniversityRef.model_validate(universities[t.university_id]) if t.university_id in universities else None,
            created_at=t.created_at,
            version=t.version,
        )
        for t in tasks
    ]


# ---------- routes ----------

@router.post('/tasks', response_model=TaskOut, status_code=201, summary='Создать задачу')
def create_task(data: TaskCreate, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    creator_id = auth.user.id
    if data.creator_id is not None and data.creator_id != auth.user.id:
        if not sees_all(auth.user):
            raise AppError(ErrorCode.FORBIDDEN, 'Создавать задачи от имени другого пользователя может только руководитель или администратор')
        creator = db.get(User, data.creator_id)
        if creator is None or not creator.is_active:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'creator_id', 'Пользователь не найден или неактивен')
        creator_id = creator.id

    university_id, launch, contract = resolve_links(db, data)
    if university_id is not None:
        university_in_scope(db, auth.user, university_id)
    members = load_members(db, data)

    parent = None
    if data.parent_task_id is not None:
        parent = db.get(Task, data.parent_task_id)
        if parent is None or not can(auth.user, TaskAction.VIEW, parent):
            raise not_found()
        if not can(auth.user, TaskAction.EDIT, parent):
            raise AppError(ErrorCode.FORBIDDEN, 'Добавлять подзадачи может только тот, кто может изменять исходную задачу')
        if parent.parent_task_id is not None:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'parent_task_id', 'Подзадача не может сама иметь подзадачи (только один уровень)')

    task = Task(
        title=data.title, description=data.description, deadline=data.deadline, planned_start=data.planned_start,
        priority=data.priority, creator_id=creator_id, university_id=university_id,
        launch_id=launch.id if launch else None, contract_id=contract.id if contract else None,
        approval_required=data.approval_required, require_checklist_complete=data.require_checklist_complete,
        parent_task_id=parent.id if parent else None,
    )
    db.add(task)
    db.flush()
    for role, users in members.items():
        for user in users:
            db.add(TaskMember(task_id=task.id, user_id=user.id, role=role))
    db.add(TaskEvent(task_id=task.id, event_type='created', actor_user_id=auth.user.id))
    record_event(db, request, auth.user, 'task.create', entity_type='task', entity_id=task.id,
                 summary=f'Создана задача «{task.title}»', payload={'title': task.title, 'university_id': university_id})
    db.commit()
    return task_out(db, task.id)


# ---------- status workflow ----------

class StatusChangeIn(BaseModel):
    to_status: TaskStatus
    comment: Description = ''
    version: int


def is_task_assignee(db, task_id, user_id):
    return bool(db.scalar(select(exists().where(
        TaskMember.task_id == task_id, TaskMember.user_id == user_id, TaskMember.role == 'assignee',
    ))))


def apply_status_change(db, request, auth, task, to_status, comment):
    """Validates and applies one status transition on an already-loaded, already-viewable `task`.

    Raises AppError on any rule violation; does not commit (bulk callers wrap several of these in
    one transaction with per-task savepoints; the single-task route commits once itself).
    """
    rule = TRANSITIONS.get((task.status, to_status))
    if rule is None:
        raise field_error(
            ErrorCode.VALIDATION_ERROR, 'to_status',
            f'Нельзя перейти из статуса «{STATUS_LABELS[task.status]}» в «{STATUS_LABELS[to_status]}»',
        )
    is_creator = task.creator_id == auth.user.id
    is_manager = sees_all(auth.user) or is_creator
    if rule == 'manager' and not is_manager:
        raise AppError(ErrorCode.FORBIDDEN)
    if rule == 'assignee' and not (is_manager or is_task_assignee(db, task.id, auth.user.id)):
        raise AppError(ErrorCode.FORBIDDEN)

    if to_status == 'awaiting_review' and not task.approval_required:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'to_status', 'Эта задача не требует согласования — её можно завершить напрямую')
    if to_status == 'completed' and task.status == 'in_progress' and task.approval_required:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'to_status', 'Для этой задачи требуется согласование: сначала отправьте её на проверку')
    if (task.status, to_status) == ('awaiting_review', 'in_progress') and not comment.strip():
        raise field_error(ErrorCode.VALIDATION_ERROR, 'comment', 'Укажите причину возврата на доработку')

    if to_status == 'completed':
        if task.require_checklist_complete:
            open_items = db.scalar(select(func.count()).select_from(TaskChecklistItem).where(
                TaskChecklistItem.task_id == task.id, TaskChecklistItem.is_done.is_(False),
            ))
            if open_items:
                raise field_error(
                    ErrorCode.VALIDATION_ERROR, 'checklist',
                    f'Не отмечены пункты чек-листа ({open_items}); отметьте их или снимите требование чек-листа',
                )
        open_subtasks = db.scalars(select(Task.title).where(
            Task.parent_task_id == task.id, Task.status.notin_(('completed', 'cancelled')),
        )).all()
        if open_subtasks:
            names = ', '.join(f'«{t}»' for t in open_subtasks[:5])
            raise field_error(ErrorCode.VALIDATION_ERROR, 'subtasks', f'Не завершены подзадачи: {names}')

    previous = task.status
    task.status = to_status
    if to_status == 'completed':
        task.completed_at = utcnow()
        task.completed_by_user_id = auth.user.id
    elif previous == 'completed':
        task.completed_at = None
        task.completed_by_user_id = None
    db.add(TaskEvent(
        task_id=task.id, event_type='status_change', actor_user_id=auth.user.id,
        from_value=previous, to_value=to_status, comment=comment,
    ))
    record_event(db, request, auth.user, 'task.status_change', entity_type='task', entity_id=task.id,
                 summary=f'«{task.title}»: статус «{STATUS_LABELS[previous]}» → «{STATUS_LABELS[to_status]}»',
                 payload={'from': previous, 'to': to_status, 'has_comment': bool(comment.strip())})


@router.post('/tasks/{id}/status', response_model=TaskOut, summary='Сменить статус задачи')
def change_status(id: int, data: StatusChangeIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    if task.version != data.version:
        raise field_error(ErrorCode.CONFLICT, 'version', 'Задача уже изменена другим пользователем; обновите страницу')
    apply_status_change(db, request, auth, task, data.to_status, data.comment)
    try:
        db.commit()
    except StaleDataError as error:
        db.rollback()
        raise field_error(ErrorCode.CONFLICT, 'version', 'Задача уже изменена другим пользователем; обновите страницу') from error
    return task_out(db, task.id)


# ---------- checklist ----------

class ChecklistItemIn(BaseModel):
    title: Title
    assignee_user_id: int | None = Field(default=None, gt=0)
    deadline: date | None = None


class ChecklistItemPatch(BaseModel):
    title: Title | None = None
    assignee_user_id: int | None = Field(default=None, gt=0)
    deadline: date | None = None
    is_done: bool | None = None


class ChecklistOrderIn(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=200)


def checklist_item_out(db, item):
    assignee = db.get(User, item.assignee_user_id) if item.assignee_user_id else None
    completed_by = db.get(User, item.completed_by_user_id) if item.completed_by_user_id else None
    return ChecklistItemOut(
        id=item.id, title=item.title, position=item.position, is_done=item.is_done,
        assignee=PersonOut.model_validate(assignee) if assignee else None, deadline=item.deadline,
        completed_by=PersonOut.model_validate(completed_by) if completed_by else None, completed_at=item.completed_at,
    )


def check_active_user(db, user_id, field):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise field_error(ErrorCode.VALIDATION_ERROR, field, 'Пользователь не найден или неактивен')


def check_active_user_ids(db, user_ids, field):
    count = db.scalar(select(func.count()).select_from(User).where(User.id.in_(user_ids), User.is_active.is_(True)))
    if count != len(user_ids):
        raise field_error(ErrorCode.VALIDATION_ERROR, field, 'Один или несколько пользователей не найдены или неактивны')


def load_task_for_checklist(db, task_id, auth, *, require_edit):
    task = db.get(Task, task_id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    if require_edit and not can(auth.user, TaskAction.EDIT_CHECKLIST, task):
        raise AppError(ErrorCode.FORBIDDEN)
    return task


@router.post('/tasks/{id}/checklist-items', response_model=ChecklistItemOut, status_code=201, summary='Добавить пункт чек-листа')
def add_checklist_item(id: int, data: ChecklistItemIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = load_task_for_checklist(db, id, auth, require_edit=True)
    if data.assignee_user_id is not None:
        check_active_user(db, data.assignee_user_id, 'assignee_user_id')
    count = db.scalar(select(func.count()).select_from(TaskChecklistItem).where(TaskChecklistItem.task_id == task.id))
    item = TaskChecklistItem(
        task_id=task.id, title=data.title, position=count,
        assignee_user_id=data.assignee_user_id, deadline=data.deadline,
    )
    db.add(item)
    db.flush()
    db.add(TaskEvent(task_id=task.id, event_type='checklist_item_added', actor_user_id=auth.user.id, to_value=data.title[:100]))
    record_event(db, request, auth.user, 'task.checklist_item_add', entity_type='task', entity_id=task.id,
                 summary=f'«{task.title}»: добавлен пункт чек-листа «{data.title}»', payload={'title': data.title})
    db.commit()
    return checklist_item_out(db, item)


@router.patch('/checklist-items/{item_id}', response_model=ChecklistItemOut, summary='Изменить пункт чек-листа')
def update_checklist_item(item_id: int, data: ChecklistItemPatch, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    item = db.get(TaskChecklistItem, item_id)
    if item is None:
        raise not_found()
    task = load_task_for_checklist(db, item.task_id, auth, require_edit=False)

    changes = {}
    if data.is_done is not None and data.is_done != item.is_done:
        is_creator = task.creator_id == auth.user.id
        allowed = sees_all(auth.user) or is_creator
        if not allowed and is_task_assignee(db, task.id, auth.user.id):
            allowed = item.assignee_user_id in (None, auth.user.id)
        if not allowed:
            raise AppError(ErrorCode.FORBIDDEN)
        changes['is_done'] = {'from': item.is_done, 'to': data.is_done}
        item.is_done = data.is_done
        item.completed_by_user_id = auth.user.id if data.is_done else None
        item.completed_at = utcnow() if data.is_done else None

    other = data.model_dump(exclude={'is_done'}, exclude_none=True)
    if other:
        if not can(auth.user, TaskAction.EDIT_CHECKLIST, task):
            raise AppError(ErrorCode.FORBIDDEN)
        if 'assignee_user_id' in other:
            check_active_user(db, other['assignee_user_id'], 'assignee_user_id')
        for name, value in other.items():
            if getattr(item, name) != value:
                changes[name] = {'from': getattr(item, name), 'to': value}
                setattr(item, name, value)

    if changes:
        db.add(TaskEvent(
            task_id=task.id, actor_user_id=auth.user.id,
            event_type='checklist_item_completed' if 'is_done' in changes else 'checklist_item_updated',
        ))
        record_event(db, request, auth.user, 'task.checklist_item_update', entity_type='task', entity_id=task.id,
                     summary=f'«{task.title}»: изменён пункт чек-листа «{item.title}»', payload=changes)
        db.commit()
    return checklist_item_out(db, item)


@router.delete('/checklist-items/{item_id}', status_code=204, summary='Удалить пункт чек-листа')
def delete_checklist_item(item_id: int, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    item = db.get(TaskChecklistItem, item_id)
    if item is None:
        raise not_found()
    task = load_task_for_checklist(db, item.task_id, auth, require_edit=True)
    db.delete(item)
    db.add(TaskEvent(task_id=task.id, event_type='checklist_item_removed', actor_user_id=auth.user.id, from_value=item.title[:100]))
    record_event(db, request, auth.user, 'task.checklist_item_delete', entity_type='task', entity_id=task.id,
                 summary=f'«{task.title}»: удалён пункт чек-листа «{item.title}»', payload={'title': item.title})
    db.commit()


@router.put('/tasks/{id}/checklist-order', response_model=list[ChecklistItemOut], summary='Изменить порядок пунктов чек-листа')
def reorder_checklist(id: int, data: ChecklistOrderIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = load_task_for_checklist(db, id, auth, require_edit=True)
    items = {i.id: i for i in db.scalars(select(TaskChecklistItem).where(TaskChecklistItem.task_id == task.id))}
    if set(data.item_ids) != set(items) or len(data.item_ids) != len(items):
        raise field_error(ErrorCode.VALIDATION_ERROR, 'item_ids', 'Перечислите все пункты чек-листа ровно по одному разу')
    # Two-phase: negate first so the (task_id, position) unique constraint never sees a transient collision.
    for item in items.values():
        item.position = -(item.position + 1)
    db.flush()
    for position, item_id in enumerate(data.item_ids):
        items[item_id].position = position
    record_event(db, request, auth.user, 'task.checklist_reorder', entity_type='task', entity_id=task.id,
                 summary=f'«{task.title}»: изменён порядок пунктов чек-листа', payload={'item_ids': data.item_ids})
    db.commit()
    return [checklist_item_out(db, items[i]) for i in data.item_ids]


# ---------- subtasks ----------

@router.get('/tasks/{id}/subtasks', response_model=list[TaskListItemOut], summary='Подзадачи')
def list_subtasks(id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    rows = db.scalars(select(Task).where(Task.parent_task_id == task.id).order_by(Task.id)).all()
    return task_list_items(db, rows)


# ---------- comments and attachments ----------

class CommentOut(BaseModel):
    id: int
    author: PersonOut | None
    body: str
    created_at: datetime
    attachments: list[dict]


def comment_out(db, comment):
    return comments_out(db, [comment])[0]


def comments_out(db, comments):
    """Batch-loads authors/attachments for a page of comments instead of querying per row."""
    comment_ids = [c.id for c in comments]
    author_ids = {c.author_user_id for c in comments if c.author_user_id}
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids)))} if author_ids else {}
    attachments = db.scalars(select(TaskAttachment).where(TaskAttachment.comment_id.in_(comment_ids))).all() if comment_ids else []
    attachments_by_comment = {}
    for a in attachments:
        attachments_by_comment.setdefault(a.comment_id, []).append(a)
    return [
        CommentOut(
            id=c.id,
            author=PersonOut.model_validate(authors[c.author_user_id]) if c.author_user_id in authors else None,
            body=c.body,
            created_at=c.created_at,
            attachments=[
                {'id': a.id, 'filename': a.filename, 'content_type': a.content_type, 'size_bytes': a.size_bytes}
                for a in attachments_by_comment.get(c.id, [])
            ],
        )
        for c in comments
    ]


@router.get('/tasks/{id}/comments', response_model=list[CommentOut], summary='Комментарии к задаче')
def list_comments(id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    comments = db.scalars(select(TaskComment).where(TaskComment.task_id == task.id).order_by(TaskComment.created_at)).all()
    return comments_out(db, comments)


@router.post('/tasks/{id}/comments', response_model=CommentOut, status_code=201, summary='Добавить комментарий',
             description=f'`multipart/form-data`. Не больше {MAX_ATTACHMENTS} файлов по 20 МБ; форматы: {ALLOWED_TYPES_TEXT}.')
def add_comment(
    id: int,
    request: Request,
    body: Annotated[str, Form()] = '',
    files: Annotated[list[UploadFile] | None, File()] = None,
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    body = body.strip()
    uploads = [u for u in files or [] if u.filename]
    if not body and not uploads:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'body', 'Комментарий должен содержать текст или файл')
    if len(body) > MAX_COMMENT_LENGTH:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'body', f'Комментарий длиннее {MAX_COMMENT_LENGTH} символов')
    if len(uploads) > MAX_ATTACHMENTS:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'files', f'Не больше {MAX_ATTACHMENTS} файлов за один комментарий')

    directory = Path(request.app.state.settings.attachments_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stored = []
    try:
        comment = TaskComment(task_id=task.id, author_user_id=auth.user.id, body=body)
        db.add(comment)
        db.flush()
        for upload in uploads:
            filename, content_type, size, sha256, key, path = store_upload(upload, directory)
            stored.append(path)
            db.add(TaskAttachment(
                task_id=task.id, comment_id=comment.id, filename=filename, content_type=content_type,
                size_bytes=size, sha256=sha256, storage_key=key, uploaded_by_user_id=auth.user.id,
            ))
        db.add(TaskEvent(task_id=task.id, event_type='comment_added', actor_user_id=auth.user.id))
        # Comments may hold personal data: the audit event records only that one was added, never the text.
        record_event(db, request, auth.user, 'task.comment_add', entity_type='task', entity_id=task.id,
                     summary=f'«{task.title}»: добавлен комментарий', payload={'has_attachments': bool(uploads)})
        db.commit()
    except BaseException:
        db.rollback()
        for path in stored:
            path.unlink(missing_ok=True)
        raise
    comment = db.scalar(select(TaskComment).where(TaskComment.id == comment.id))
    return comment_out(db, comment)


# ---------- activity ----------

class ActivityEventOut(BaseModel):
    id: int
    event_type: str
    actor: PersonOut | None
    from_value: str | None
    to_value: str | None
    comment: str
    created_at: datetime


@router.get('/tasks/{id}/activity', response_model=list[ActivityEventOut], summary='Лента событий задачи')
def list_activity(id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())).all()
    actor_ids = {e.actor_user_id for e in events if e.actor_user_id}
    actors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(actor_ids)))} if actor_ids else {}
    return [
        ActivityEventOut(
            id=e.id, event_type=e.event_type,
            actor=PersonOut.model_validate(actors[e.actor_user_id]) if e.actor_user_id in actors else None,
            from_value=e.from_value, to_value=e.to_value, comment=e.comment, created_at=e.created_at,
        )
        for e in events
    ]


@router.get('/tasks/assignable-users', response_model=list[PersonOut], summary='Пользователи, доступные для назначения на задачу',
            dependencies=[Depends(any_role)])
def assignable_users(db: Session = Depends(get_db)):
    # Deliberately not the more sensitive GET /users (supervisor/admin only, includes email and roles):
    # any CRM user needs to pick assignees/participants/observers when creating a task, so this is
    # scoped to just {id, full_name} for everyone (docs/design/tasks.md).
    return db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()


DeadlinePreset = Literal['overdue', 'today', 'this_week', 'next_week', 'no_deadline']


class TaskFilters:
    """Query params shared by the List view, counters and Deadline view, so the three always agree
    on what a given filter combination means (docs/design/tasks.md)."""

    def __init__(
        self,
        status: list[TaskStatus] | None = Query(None),
        priority: list[Priority] | None = Query(None),
        creator_id: int | None = Query(None, gt=0),
        assignee_id: int | None = Query(None, gt=0),
        participant_id: int | None = Query(None, gt=0),
        observer_id: int | None = Query(None, gt=0),
        university_id: int | None = Query(None, gt=0),
        launch_id: int | None = Query(None, gt=0),
        contract_id: int | None = Query(None, gt=0),
        deadline_from: date | None = None,
        deadline_to: date | None = None,
        deadline_preset: DeadlinePreset | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        has_checklist: bool | None = None,
        active: bool | None = None,
    ):
        self.status = status
        self.priority = priority
        self.creator_id = creator_id
        self.assignee_id = assignee_id
        self.participant_id = participant_id
        self.observer_id = observer_id
        self.university_id = university_id
        self.launch_id = launch_id
        self.contract_id = contract_id
        self.deadline_from = deadline_from
        self.deadline_to = deadline_to
        self.deadline_preset = deadline_preset
        self.created_from = created_from
        self.created_to = created_to
        self.has_checklist = has_checklist
        self.active = active


def week_bounds(today):
    start = today - timedelta(days=today.weekday())  # Monday
    return start, start + timedelta(days=6)  # Sunday


def _member_filter(role, user_id):
    return exists().where(TaskMember.task_id == Task.id, TaskMember.user_id == user_id, TaskMember.role == role)


def apply_scope(query, scope, user):
    if scope == 'mine':
        return query.where(or_(Task.creator_id == user.id, exists().where(TaskMember.task_id == Task.id, TaskMember.user_id == user.id)))
    if scope == 'created':
        return query.where(Task.creator_id == user.id)
    if scope in SCOPE_MEMBER_ROLE:
        return query.where(_member_filter(SCOPE_MEMBER_ROLE[scope], user.id))
    return query  # 'team'/'all': no extra restriction beyond visible_tasks_query.


def apply_filters(query, filters, *, today=None):
    today = today or date.today()
    if filters.status:
        query = query.where(Task.status.in_(filters.status))
    if filters.priority:
        query = query.where(Task.priority.in_(filters.priority))
    if filters.creator_id:
        query = query.where(Task.creator_id == filters.creator_id)
    if filters.assignee_id:
        query = query.where(_member_filter('assignee', filters.assignee_id))
    if filters.participant_id:
        query = query.where(_member_filter('participant', filters.participant_id))
    if filters.observer_id:
        query = query.where(_member_filter('observer', filters.observer_id))
    if filters.university_id:
        query = query.where(Task.university_id == filters.university_id)
    if filters.launch_id:
        query = query.where(Task.launch_id == filters.launch_id)
    if filters.contract_id:
        query = query.where(Task.contract_id == filters.contract_id)
    if filters.deadline_from:
        query = query.where(Task.deadline >= filters.deadline_from)
    if filters.deadline_to:
        query = query.where(Task.deadline <= filters.deadline_to)
    if filters.deadline_preset:
        week_start, week_end = week_bounds(today)
        if filters.deadline_preset == 'overdue':
            query = query.where(Task.deadline < today, Task.status.notin_(('completed', 'cancelled')))
        elif filters.deadline_preset == 'today':
            query = query.where(Task.deadline == today)
        elif filters.deadline_preset == 'this_week':
            query = query.where(Task.deadline >= today, Task.deadline <= week_end)
        elif filters.deadline_preset == 'next_week':
            query = query.where(Task.deadline > week_end, Task.deadline <= week_end + timedelta(days=7))
        elif filters.deadline_preset == 'no_deadline':
            query = query.where(Task.deadline.is_(None))
    if filters.created_from:
        query = query.where(Task.created_at >= filters.created_from)
    if filters.created_to:
        query = query.where(Task.created_at < filters.created_to + timedelta(days=1))
    if filters.has_checklist is not None:
        clause = exists().where(TaskChecklistItem.task_id == Task.id)
        query = query.where(clause if filters.has_checklist else ~clause)
    if filters.active is not None:
        clause = Task.status.notin_(('completed', 'cancelled'))
        query = query.where(clause if filters.active else ~clause)
    return query


def base_task_query(auth, scope):
    if scope in ('team', 'all') and not sees_all(auth.user):
        raise AppError(ErrorCode.FORBIDDEN, 'Эта область видна только руководителю или администратору')
    query = select(Task).where(visible_tasks_query(auth.user), Task.archived_at.is_(None))
    return apply_scope(query, scope, auth.user)


@router.get('/tasks', response_model=TaskPage, summary='Список задач')
def list_tasks(
    scope: Scope = 'mine',
    search: str = '',
    sort: str = '-created_at',
    limit: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    filters: TaskFilters = Depends(),
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    field = sort[1:] if sort.startswith('-') else sort
    if field not in SORT_COLUMNS:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'sort', 'Недопустимое поле сортировки')
    column = SORT_COLUMNS[field]
    order = column.desc() if sort.startswith('-') else column.asc()

    query = base_task_query(auth, scope)
    query = apply_filters(query, filters)
    if search.strip():
        pattern = like_pattern(search.strip())
        query = query.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(order, Task.id.desc()).offset(offset).limit(limit)).all()
    return TaskPage(items=task_list_items(db, rows), total=total or 0, limit=limit, offset=offset)


class CountersOut(BaseModel):
    open: int
    overdue: int
    due_today: int
    awaiting_review: int
    no_deadline: int


@router.get('/tasks/counters', response_model=CountersOut, summary='Счётчики для рабочего пространства задач')
def task_counters(scope: Scope = 'mine', auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    today = date.today()
    base = base_task_query(auth, scope)
    open_clause = Task.status.notin_(('completed', 'cancelled'))

    def count(*clauses):
        return db.scalar(select(func.count()).select_from(base.where(*clauses).subquery())) or 0

    return CountersOut(
        open=count(open_clause),
        overdue=count(open_clause, Task.deadline < today),
        due_today=count(open_clause, Task.deadline == today),
        awaiting_review=count(Task.status == 'awaiting_review'),
        no_deadline=count(open_clause, Task.deadline.is_(None)),
    )


DEADLINE_GROUPS = ('overdue', 'today', 'this_week', 'next_week', 'later', 'no_deadline', 'completed')


class DeadlineGroupOut(BaseModel):
    group: str
    total: int
    items: list[TaskListItemOut]


@router.get('/tasks/deadline-groups', response_model=list[DeadlineGroupOut], summary='Задачи по срокам')
def deadline_groups(
    scope: Scope = 'mine',
    search: str = '',
    filters: TaskFilters = Depends(),
    group_limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    today = date.today()
    week_start, week_end = week_bounds(today)
    base = base_task_query(auth, scope)
    base = apply_filters(base, filters, today=today)
    if search.strip():
        pattern = like_pattern(search.strip())
        base = base.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))

    active = Task.status.notin_(('completed', 'cancelled'))
    clauses = {
        'completed': (Task.status == 'completed',),
        'overdue': (active, Task.deadline.is_not(None), Task.deadline < today),
        'today': (active, Task.deadline == today),
        'this_week': (active, Task.deadline > today, Task.deadline <= week_end),
        'next_week': (active, Task.deadline > week_end, Task.deadline <= week_end + timedelta(days=7)),
        'later': (active, Task.deadline > week_end + timedelta(days=7)),
        'no_deadline': (active, Task.deadline.is_(None)),
    }
    results = []
    for group in DEADLINE_GROUPS:
        group_query = base.where(*clauses[group])
        total = db.scalar(select(func.count()).select_from(group_query.subquery())) or 0
        rows = db.scalars(group_query.order_by(Task.deadline.asc().nulls_last(), Task.id.desc()).limit(group_limit)).all()
        results.append(DeadlineGroupOut(group=group, total=total, items=task_list_items(db, rows)))
    return results


class PreferencesOut(BaseModel):
    list_columns: list[str] | None
    planner_columns: list[str] | None
    planner_positions: dict | None


class PreferencesIn(BaseModel):
    list_columns: list[str] | None = None
    planner_columns: list[str] | None = None
    planner_positions: dict | None = None


@router.get('/tasks/preferences', response_model=PreferencesOut, summary='Настройки рабочего пространства задач')
def get_preferences(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    prefs = db.get(TaskUserPreferences, auth.user.id)
    if prefs is None:
        return PreferencesOut(list_columns=None, planner_columns=None, planner_positions=None)
    return PreferencesOut(list_columns=prefs.list_columns, planner_columns=prefs.planner_columns, planner_positions=prefs.planner_positions)


@router.put('/tasks/preferences', response_model=PreferencesOut, summary='Сохранить настройки рабочего пространства задач')
def set_preferences(data: PreferencesIn, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    """Each of the three fields is saved independently — the List view's column picker, the planner's
    column picker and its drag positions each call this without the other two, so only fields the
    client actually sent are touched (unsent fields keep their stored value, not reset to null)."""
    prefs = db.get(TaskUserPreferences, auth.user.id)
    if prefs is None:
        prefs = TaskUserPreferences(user_id=auth.user.id)
        db.add(prefs)
    for field in data.model_fields_set:
        setattr(prefs, field, getattr(data, field))
    prefs.updated_at = utcnow()
    db.commit()
    return PreferencesOut(list_columns=prefs.list_columns, planner_columns=prefs.planner_columns, planner_positions=prefs.planner_positions)


@router.get('/tasks/{id}', response_model=TaskOut, summary='Задача')
def get_task(id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    return task_out(db, task.id)


@router.patch('/tasks/{id}', response_model=TaskOut, summary='Изменить задачу')
def update_task(id: int, data: TaskPatch, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    if not can(auth.user, TaskAction.EDIT, task):
        raise AppError(ErrorCode.FORBIDDEN)
    if task.version != data.version:
        raise field_error(ErrorCode.CONFLICT, 'version', 'Задача уже изменена другим пользователем; обновите страницу')

    changes = {
        name: {'from': getattr(task, name), 'to': value}
        for name, value in data.model_dump(exclude={'version'}, exclude_none=True).items()
        if getattr(task, name) != value
    }
    if changes:
        for name, change in changes.items():
            setattr(task, name, change['to'])
        db.add(TaskEvent(task_id=task.id, event_type='updated', actor_user_id=auth.user.id))
        record_event(db, request, auth.user, 'task.update', entity_type='task', entity_id=task.id,
                     summary=f'Изменена задача «{task.title}»', payload=changes)
        try:
            db.commit()
        except StaleDataError as error:
            db.rollback()
            raise field_error(ErrorCode.CONFLICT, 'version', 'Задача уже изменена другим пользователем; обновите страницу') from error
    return task_out(db, task.id)


@router.put('/tasks/{id}/members', response_model=TaskOut, summary='Назначить участников')
def set_members(id: int, data: MembersIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    task = db.get(Task, id)
    if task is None or not can(auth.user, TaskAction.VIEW, task):
        raise not_found()
    if not can(auth.user, TaskAction.REASSIGN, task):
        raise AppError(ErrorCode.FORBIDDEN)
    members = load_members(db, data)

    db.execute(delete(TaskMember).where(TaskMember.task_id == task.id))
    for role, users in members.items():
        for user in users:
            db.add(TaskMember(task_id=task.id, user_id=user.id, role=role))
    db.add(TaskEvent(task_id=task.id, event_type='reassignment', actor_user_id=auth.user.id))
    record_event(db, request, auth.user, 'task.members_update', entity_type='task', entity_id=task.id,
                 summary=f'Изменён состав участников задачи «{task.title}»',
                 payload={role: [u.id for u in users] for role, users in members.items()})
    db.commit()
    return task_out(db, task.id)


# ---------- bulk actions ----------
#
# The server evaluates permission for every selected task individually (spec requirement) — a
# selection spanning tasks the user may and may not act on partially succeeds, never all-or-nothing.
# Each task's change runs in its own savepoint so one failure cannot roll back the others; bulk
# actions do not take a `version` (impractical to require the client to know every selected task's
# current version), so they are not protected by the same optimistic-concurrency check as the
# single-task endpoints (D-170).

TaskIds = Annotated[list[int], Field(min_length=1, max_length=200)]


class BulkSkip(BaseModel):
    id: int
    reason: str


class BulkResult(BaseModel):
    updated: list[int]
    skipped: list[BulkSkip]


class BulkStatusIn(BaseModel):
    task_ids: TaskIds
    to_status: TaskStatus
    comment: Description = ''


class BulkDeadlineIn(BaseModel):
    task_ids: TaskIds
    deadline: date | None = None


class BulkMembersIn(BaseModel):
    task_ids: TaskIds
    add_assignee_ids: list[int] = Field(default_factory=list, max_length=50)
    remove_assignee_ids: list[int] = Field(default_factory=list, max_length=50)


class BulkArchiveIn(BaseModel):
    task_ids: TaskIds
    confirm: bool = False


class BulkRestoreIn(BaseModel):
    task_ids: TaskIds


def run_bulk(db, task_ids, auth, action):
    """Applies `action(task)` to each task in its own savepoint; `action` raises AppError to skip."""
    updated = []
    skipped = []
    for task_id in task_ids:
        try:
            with db.begin_nested():
                task = db.get(Task, task_id)
                if task is None or not can(auth.user, TaskAction.VIEW, task):
                    raise AppError(ErrorCode.RECORD_NOT_FOUND)
                action(task)
        except AppError as error:
            skipped.append(BulkSkip(id=task_id, reason=error.message))
        else:
            updated.append(task_id)
    db.commit()
    return BulkResult(updated=updated, skipped=skipped)


@router.post('/tasks/bulk/status', response_model=BulkResult, summary='Массовая смена статуса')
def bulk_status(data: BulkStatusIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    def action(task):
        apply_status_change(db, request, auth, task, data.to_status, data.comment)
    return run_bulk(db, data.task_ids, auth, action)


@router.post('/tasks/bulk/deadline', response_model=BulkResult, summary='Массовое изменение срока')
def bulk_deadline(data: BulkDeadlineIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    def action(task):
        if not can(auth.user, TaskAction.CHANGE_DEADLINE, task):
            raise AppError(ErrorCode.FORBIDDEN)
        if task.deadline != data.deadline:
            previous = task.deadline
            task.deadline = data.deadline
            db.add(TaskEvent(task_id=task.id, event_type='updated', actor_user_id=auth.user.id))
            record_event(db, request, auth.user, 'task.update', entity_type='task', entity_id=task.id,
                         summary=f'Изменена задача «{task.title}»',
                         payload={'deadline': {'from': previous.isoformat() if previous else None,
                                                'to': data.deadline.isoformat() if data.deadline else None}})
    return run_bulk(db, data.task_ids, auth, action)


@router.post('/tasks/bulk/members', response_model=BulkResult, summary='Массовое назначение исполнителей')
def bulk_members(data: BulkMembersIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    add_ids = set(data.add_assignee_ids)
    remove_ids = set(data.remove_assignee_ids)
    if add_ids:
        check_active_user_ids(db, add_ids, 'add_assignee_ids')

    def action(task):
        if not can(auth.user, TaskAction.REASSIGN, task):
            raise AppError(ErrorCode.FORBIDDEN)
        if remove_ids:
            db.execute(delete(TaskMember).where(
                TaskMember.task_id == task.id, TaskMember.role == 'assignee', TaskMember.user_id.in_(remove_ids),
            ))
        if add_ids:
            existing = set(db.scalars(select(TaskMember.user_id).where(
                TaskMember.task_id == task.id, TaskMember.role == 'assignee', TaskMember.user_id.in_(add_ids),
            )))
            for user_id in add_ids - existing:
                db.add(TaskMember(task_id=task.id, user_id=user_id, role='assignee'))
        if add_ids or remove_ids:
            db.add(TaskEvent(task_id=task.id, event_type='reassignment', actor_user_id=auth.user.id))
            record_event(db, request, auth.user, 'task.members_update', entity_type='task', entity_id=task.id,
                         summary=f'Изменён состав исполнителей задачи «{task.title}»',
                         payload={'added': sorted(add_ids), 'removed': sorted(remove_ids)})
    return run_bulk(db, data.task_ids, auth, action)


@router.post('/tasks/bulk/archive', response_model=BulkResult, summary='Массовая архивация')
def bulk_archive(data: BulkArchiveIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    if not data.confirm:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'confirm', 'Подтвердите архивацию')

    def action(task):
        if not can(auth.user, TaskAction.ARCHIVE, task):
            raise AppError(ErrorCode.FORBIDDEN)
        if task.archived_at is None:
            task.archived_at = utcnow()
            task.archived_by_user_id = auth.user.id
            db.add(TaskEvent(task_id=task.id, event_type='archived', actor_user_id=auth.user.id))
            record_event(db, request, auth.user, 'task.archive', entity_type='task', entity_id=task.id,
                         summary=f'Архивирована задача «{task.title}»', payload={})
    return run_bulk(db, data.task_ids, auth, action)


@router.post('/tasks/bulk/restore', response_model=BulkResult, summary='Восстановить из архива')
def bulk_restore(data: BulkRestoreIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    def action(task):
        if not can(auth.user, TaskAction.ARCHIVE, task):
            raise AppError(ErrorCode.FORBIDDEN)
        if task.archived_at is not None:
            task.archived_at = None
            task.archived_by_user_id = None
            db.add(TaskEvent(task_id=task.id, event_type='restored', actor_user_id=auth.user.id))
            record_event(db, request, auth.user, 'task.restore', entity_type='task', entity_id=task.id,
                         summary=f'Восстановлена задача «{task.title}»', payload={})
    return run_bulk(db, data.task_ids, auth, action)
