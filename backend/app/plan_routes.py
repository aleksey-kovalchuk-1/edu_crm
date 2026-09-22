"""Task plan templates — the central use case (docs/design/tasks.md): create/edit/reorder/preview a
reusable template, then generate its steps as ordinary tasks for one university in a single
transaction. A generated run stores a full snapshot of the template at that moment, so later
template edits never rewrite tasks a past run already created.
"""
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import PersonOut, not_found, sees_all, university_in_scope
from .db import get_db
from .errors import AppError, ErrorCode
from .models import (
    Launch, Task, TaskChecklistItem, TaskEvent, TaskMember, TaskPlanRun, TaskPlanTemplate,
    TaskPlanTemplateStep, TaskPlanTemplateStepChecklistItem, University, UniversityManager, User, utcnow,
)
from .task_routes import task_out
from .task_policy import TaskAction, can, visible_tasks_query
from .workflows import STAGE_GROUPS, launch_in_scope, stage_group

router = APIRouter(prefix='/api/v1', tags=['Шаблоны планов задач'])
any_role = require_roles(*ALL_ROLES)
template_editor = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
AssigneeRule = Literal['specific_user', 'interaction_owner', 'university_manager', 'plan_creator', 'manual']
OffsetUnit = Literal['calendar', 'business']
Priority = Literal['low', 'normal', 'high', 'urgent']

ASSIGNEE_RULE_LABELS = {
    'specific_user': 'Конкретный пользователь',
    'interaction_owner': 'Ответственный по взаимодействию',
    'university_manager': 'Менеджер вуза',
    'plan_creator': 'Автор плана',
    'manual': 'Назначается вручную',
}


def field_error(code, field, message):
    return AppError(code, message, [{'field': field, 'message': message, 'type': 'value_error'}])


def add_offset(start, days, unit):
    """`days` calendar or business days after `start` (business days skip Sat/Sun)."""
    if unit == 'calendar' or not days:
        return start + timedelta(days=days)
    result = start
    remaining = days
    step = 1 if days > 0 else -1
    while remaining != 0:
        result += timedelta(days=step)
        if result.weekday() < 5:
            remaining -= step
    return result


# ---------- schemas ----------

class TemplateStepChecklistOut(BaseModel):
    id: int
    title: str
    position: int


class TemplateStepOut(BaseModel):
    id: int
    position: int
    title: str
    description: str
    assignee_rule: AssigneeRule
    assignee_rule_user_id: int | None
    start_offset_days: int
    deadline_offset_days: int | None
    offset_unit: OffsetUnit
    priority: Priority
    approval_required: bool
    is_optional: bool
    category: int | None
    depends_on_step_id: int | None
    checklist_items: list[TemplateStepChecklistOut]


class TemplateOut(BaseModel):
    id: int
    name: str
    description: str
    is_active: bool
    created_at: datetime
    steps: list[TemplateStepOut]


class TemplateStepIn(BaseModel):
    title: Title
    description: Description = ''
    assignee_rule: AssigneeRule
    assignee_rule_user_id: int | None = Field(default=None, gt=0)
    start_offset_days: int = Field(0, ge=0)
    deadline_offset_days: int | None = Field(default=None, ge=0)
    offset_unit: OffsetUnit = 'calendar'
    priority: Priority = 'normal'
    approval_required: bool = False
    is_optional: bool = False
    category: int | None = Field(default=None, ge=0, le=4)
    # Index into the *same* create request's `steps` list (a template's steps don't have ids yet).
    depends_on_position: int | None = Field(default=None, ge=0)
    checklist_items: list[Title] = Field(default_factory=list, max_length=50)


class TemplateIn(BaseModel):
    name: Name
    description: Description = ''
    steps: list[TemplateStepIn] = Field(default_factory=list, max_length=100)


class TemplatePatchIn(BaseModel):
    name: Name | None = None
    description: Description | None = None
    is_active: bool | None = None


class TemplateStepAddIn(BaseModel):
    title: Title
    description: Description = ''
    assignee_rule: AssigneeRule
    assignee_rule_user_id: int | None = Field(default=None, gt=0)
    start_offset_days: int = Field(0, ge=0)
    deadline_offset_days: int | None = Field(default=None, ge=0)
    offset_unit: OffsetUnit = 'calendar'
    priority: Priority = 'normal'
    approval_required: bool = False
    is_optional: bool = False
    category: int | None = Field(default=None, ge=0, le=4)
    depends_on_step_id: int | None = Field(default=None, gt=0)
    checklist_items: list[Title] = Field(default_factory=list, max_length=50)


class TemplateStepPatchIn(BaseModel):
    title: Title | None = None
    description: Description | None = None
    assignee_rule: AssigneeRule | None = None
    assignee_rule_user_id: int | None = Field(default=None, gt=0)
    start_offset_days: int | None = Field(default=None, ge=0)
    deadline_offset_days: int | None = None
    offset_unit: OffsetUnit | None = None
    priority: Priority | None = None
    approval_required: bool | None = None
    is_optional: bool | None = None
    category: int | None = Field(default=None, ge=0, le=4)
    depends_on_step_id: int | None = Field(default=None, gt=0)
    checklist_items: list[Title] | None = Field(default=None, max_length=50)


class StepOrderIn(BaseModel):
    step_ids: list[int] = Field(min_length=1, max_length=100)


# ---------- helpers ----------

def checklist_out(item):
    return TemplateStepChecklistOut(id=item.id, title=item.title, position=item.position)


def step_out(step):
    return TemplateStepOut(
        id=step.id, position=step.position, title=step.title, description=step.description,
        assignee_rule=step.assignee_rule, assignee_rule_user_id=step.assignee_rule_user_id,
        start_offset_days=step.start_offset_days, deadline_offset_days=step.deadline_offset_days,
        offset_unit=step.offset_unit, priority=step.priority, approval_required=step.approval_required,
        is_optional=step.is_optional, category=step.category, depends_on_step_id=step.depends_on_step_id,
        checklist_items=[checklist_out(i) for i in sorted(step.checklist_items, key=lambda i: i.position)],
    )


def template_out(db, template):
    return templates_out(db, [template])[0]


def templates_out(db, templates):
    """Batch-loads steps (with their checklist items) for a page of templates instead of querying per row."""
    template_ids = [t.id for t in templates]
    steps = db.scalars(
        select(TaskPlanTemplateStep).where(TaskPlanTemplateStep.template_id.in_(template_ids))
        .options(selectinload(TaskPlanTemplateStep.checklist_items)).order_by(TaskPlanTemplateStep.position)
    ).all() if template_ids else []
    steps_by_template = {}
    for s in steps:
        steps_by_template.setdefault(s.template_id, []).append(s)
    return [
        TemplateOut(
            id=t.id, name=t.name, description=t.description, is_active=t.is_active,
            created_at=t.created_at, steps=[step_out(s) for s in steps_by_template.get(t.id, [])],
        )
        for t in templates
    ]


def load_template(db, template_id, *, lock=False):
    query = select(TaskPlanTemplate).where(TaskPlanTemplate.id == template_id)
    if lock:
        query = query.with_for_update()
    template = db.scalar(query)
    if template is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    return template


def snapshot_template(db, template):
    """A plain-dict copy of the template and its steps, stored on the run so later template edits
    can never change what a past run generated."""
    steps = db.scalars(
        select(TaskPlanTemplateStep).where(TaskPlanTemplateStep.template_id == template.id)
        .options(selectinload(TaskPlanTemplateStep.checklist_items)).order_by(TaskPlanTemplateStep.position)
    ).all()
    return {
        'template_id': template.id,
        'name': template.name,
        'description': template.description,
        'steps': [
            {
                'id': s.id, 'position': s.position, 'title': s.title, 'description': s.description,
                'assignee_rule': s.assignee_rule, 'assignee_rule_user_id': s.assignee_rule_user_id,
                'start_offset_days': s.start_offset_days, 'deadline_offset_days': s.deadline_offset_days,
                'offset_unit': s.offset_unit, 'priority': s.priority, 'approval_required': s.approval_required,
                'is_optional': s.is_optional, 'category': s.category, 'depends_on_step_id': s.depends_on_step_id,
                'checklist_items': [i.title for i in sorted(s.checklist_items, key=lambda i: i.position)],
            }
            for s in steps
        ],
    }


def resolve_assignee(db, step, university_id, launch, plan_creator_id):
    """(user_id, None) if resolved, or (None, a Russian explanation) otherwise."""
    if step['assignee_rule'] == 'specific_user':
        user_id = step['assignee_rule_user_id']
        user = db.get(User, user_id) if user_id else None
        if user is None or not user.is_active:
            return None, 'В шаге не указан пользователь, или он не найден/неактивен'
        return user.id, None
    if step['assignee_rule'] == 'plan_creator':
        return plan_creator_id, None
    if step['assignee_rule'] == 'university_manager':
        managers = db.scalars(select(UniversityManager.user_id).where(UniversityManager.university_id == university_id)).all()
        if len(managers) == 1:
            return managers[0], None
        if not managers:
            return None, 'У вуза нет ответственного менеджера — назначьте вручную'
        return None, 'У вуза несколько ответственных менеджеров — назначьте вручную'
    if step['assignee_rule'] == 'interaction_owner':
        if launch is None:
            return None, 'Не выбрано взаимодействие, по которому определяется ответственный'
        matches = db.scalars(select(User.id).where(
            User.is_active.is_(True), func.lower(func.trim(User.full_name)) == launch.owner.strip().lower(),
        )).all()
        if len(matches) == 1:
            return matches[0], None
        return None, 'Не удалось однозначно сопоставить ответственного по взаимодействию с пользователем CRM'
    return None, 'Этот шаг назначается только вручную'


def resolve_plan_links(db, university_id, launch_id):
    if launch_id is None:
        return None
    launch = db.get(Launch, launch_id)
    if launch is None:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'launch_id', 'Взаимодействие не найдено')
    if launch.university_id != university_id:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'launch_id', 'Взаимодействие относится к другому учебному заведению')
    return launch


def preview_steps(db, snapshot, university_id, launch, start_date, current_user_id, overrides):
    results = []
    for step in snapshot['steps']:
        planned_start = add_offset(start_date, step['start_offset_days'], step['offset_unit'])
        deadline = add_offset(start_date, step['deadline_offset_days'], step['offset_unit']) if step['deadline_offset_days'] is not None else None
        override = overrides.get(str(step['id']))
        assignee_id, issue = (None, None)
        if override is not None:
            user = db.get(User, override)
            if user is not None and user.is_active:
                assignee_id = user.id
            else:
                issue = 'Указанный пользователь не найден или неактивен'
        else:
            assignee_id, issue = resolve_assignee(db, step, university_id, launch, current_user_id)
        assignee = db.get(User, assignee_id) if assignee_id else None
        results.append({
            'step_id': step['id'], 'title': step['title'], 'description': step['description'],
            'assignee': PersonOut.model_validate(assignee) if assignee else None, 'assignee_issue': issue,
            'planned_start': planned_start, 'deadline': deadline, 'priority': step['priority'],
            'approval_required': step['approval_required'], 'is_optional': step['is_optional'],
            'depends_on_step_id': step['depends_on_step_id'], 'checklist_items': step['checklist_items'],
        })
    return results


class PreviewStepOut(BaseModel):
    step_id: int
    title: str
    description: str
    assignee: PersonOut | None
    assignee_issue: str | None
    planned_start: date
    deadline: date | None
    priority: Priority
    approval_required: bool
    is_optional: bool
    depends_on_step_id: int | None
    checklist_items: list[str]


class PreviewOut(BaseModel):
    template_id: int
    template_name: str
    steps: list[PreviewStepOut]


class PlanRequestIn(BaseModel):
    university_id: int = Field(gt=0)
    launch_id: int | None = Field(default=None, gt=0)
    start_date: date
    assignee_overrides: dict[str, int] = Field(default_factory=dict)


class GenerateIn(PlanRequestIn):
    skip_step_ids: list[int] = Field(default_factory=list, max_length=100)


class GenerateOut(BaseModel):
    run_id: int
    tasks: list[dict]


class PlanProgressOut(BaseModel):
    total: int
    completed: int
    awaiting_review: int
    overdue: int
    blocked: int


class PlanRunOut(BaseModel):
    id: int
    template_id: int
    template_name: str
    university_id: int
    launch_id: int | None
    start_date: date
    started_by: PersonOut | None
    created_at: datetime
    progress: PlanProgressOut


def compute_progress(tasks, snapshot):
    steps_by_id = {s['id']: s for s in snapshot['steps']}
    by_step_key = {t.origin_template_step_key: t for t in tasks}
    today = date.today()
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == 'completed')
    awaiting_review = sum(1 for t in tasks if t.status == 'awaiting_review')
    overdue = sum(1 for t in tasks if t.status not in ('completed', 'cancelled') and t.deadline and t.deadline < today)
    blocked = 0
    for t in tasks:
        if t.status in ('completed', 'cancelled'):
            continue
        step = steps_by_id.get(int(t.origin_template_step_key)) if t.origin_template_step_key else None
        depends_on = step.get('depends_on_step_id') if step else None
        if depends_on is None:
            continue
        dep_task = by_step_key.get(str(depends_on))
        if dep_task is not None and dep_task.status != 'completed':
            blocked += 1
    return PlanProgressOut(total=total, completed=completed, awaiting_review=awaiting_review, overdue=overdue, blocked=blocked)


def check_university_access(db, auth, university_id):
    if not sees_all(auth.user):
        university_in_scope(db, auth.user, university_id)


# ---------- template CRUD ----------

@router.get('/task-plan-templates', response_model=list[TemplateOut], summary='Шаблоны планов задач', dependencies=[Depends(any_role)])
def list_templates(include_inactive: bool = False, db: Session = Depends(get_db)):
    query = select(TaskPlanTemplate).order_by(TaskPlanTemplate.name)
    if not include_inactive:
        query = query.where(TaskPlanTemplate.is_active.is_(True))
    return templates_out(db, db.scalars(query).all())


@router.post('/task-plan-templates', response_model=TemplateOut, status_code=201, summary='Создать шаблон плана')
def create_template(data: TemplateIn, request: Request, auth: AuthContext = Depends(template_editor), db: Session = Depends(get_db)):
    template = TaskPlanTemplate(name=data.name, description=data.description, created_by_user_id=auth.user.id)
    db.add(template)
    db.flush()
    step_ids = []
    for position, step_in in enumerate(data.steps):
        if step_in.depends_on_position is not None:
            if step_in.depends_on_position >= position:
                raise field_error(ErrorCode.VALIDATION_ERROR, f'steps.{position}.depends_on_position', 'Шаг может зависеть только от более раннего шага')
            depends_on_step_id = step_ids[step_in.depends_on_position]
        else:
            depends_on_step_id = None
        step = TaskPlanTemplateStep(
            template_id=template.id, position=position, title=step_in.title, description=step_in.description,
            assignee_rule=step_in.assignee_rule, assignee_rule_user_id=step_in.assignee_rule_user_id,
            start_offset_days=step_in.start_offset_days, deadline_offset_days=step_in.deadline_offset_days,
            offset_unit=step_in.offset_unit, priority=step_in.priority, approval_required=step_in.approval_required,
            is_optional=step_in.is_optional, category=step_in.category, depends_on_step_id=depends_on_step_id,
        )
        db.add(step)
        db.flush()
        step_ids.append(step.id)
        for item_position, title in enumerate(step_in.checklist_items):
            db.add(TaskPlanTemplateStepChecklistItem(step_id=step.id, title=title, position=item_position))
    record_event(db, request, auth.user, 'task_plan_template.create', entity_type='task_plan_template', entity_id=template.id,
                 summary=f'Создан шаблон плана «{template.name}» ({len(data.steps)} шагов)', payload={'name': data.name, 'steps': len(data.steps)})
    db.commit()
    return template_out(db, template)


@router.patch('/task-plan-templates/{template_id}', response_model=TemplateOut, summary='Изменить шаблон плана')
def update_template(template_id: int, data: TemplatePatchIn, request: Request, auth: AuthContext = Depends(template_editor), db: Session = Depends(get_db)):
    template = load_template(db, template_id, lock=True)
    changes = {name: {'from': getattr(template, name), 'to': value}
               for name, value in data.model_dump(exclude_none=True).items() if getattr(template, name) != value}
    if changes:
        for name, change in changes.items():
            setattr(template, name, change['to'])
        record_event(db, request, auth.user, 'task_plan_template.update', entity_type='task_plan_template', entity_id=template.id,
                     summary=f'Изменён шаблон плана «{template.name}»', payload=changes)
        db.commit()
    return template_out(db, template)


@router.post('/task-plan-templates/{template_id}/steps', response_model=TemplateOut, status_code=201, summary='Добавить шаг в шаблон')
def add_step(template_id: int, data: TemplateStepAddIn, request: Request, auth: AuthContext = Depends(template_editor), db: Session = Depends(get_db)):
    template = load_template(db, template_id, lock=True)
    if data.depends_on_step_id is not None:
        dep = db.get(TaskPlanTemplateStep, data.depends_on_step_id)
        if dep is None or dep.template_id != template.id:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'depends_on_step_id', 'Шаг зависимости не найден в этом шаблоне')
    count = db.scalar(select(func.count()).select_from(TaskPlanTemplateStep).where(TaskPlanTemplateStep.template_id == template.id))
    step = TaskPlanTemplateStep(
        template_id=template.id, position=count, title=data.title, description=data.description,
        assignee_rule=data.assignee_rule, assignee_rule_user_id=data.assignee_rule_user_id,
        start_offset_days=data.start_offset_days, deadline_offset_days=data.deadline_offset_days,
        offset_unit=data.offset_unit, priority=data.priority, approval_required=data.approval_required,
        is_optional=data.is_optional, category=data.category, depends_on_step_id=data.depends_on_step_id,
    )
    db.add(step)
    db.flush()
    for item_position, title in enumerate(data.checklist_items):
        db.add(TaskPlanTemplateStepChecklistItem(step_id=step.id, title=title, position=item_position))
    record_event(db, request, auth.user, 'task_plan_template.step_add', entity_type='task_plan_template', entity_id=template.id,
                 summary=f'В шаблон «{template.name}» добавлен шаг «{step.title}»', payload={'title': data.title})
    db.commit()
    return template_out(db, template)


@router.patch('/task-plan-template-steps/{step_id}', response_model=TemplateOut, summary='Изменить шаг шаблона')
def update_step(step_id: int, data: TemplateStepPatchIn, request: Request, auth: AuthContext = Depends(template_editor), db: Session = Depends(get_db)):
    step = db.get(TaskPlanTemplateStep, step_id)
    if step is None:
        raise not_found()
    template = load_template(db, step.template_id, lock=True)
    fields = data.model_dump(exclude={'checklist_items'}, exclude_none=True)
    changes = {name: {'from': getattr(step, name), 'to': value} for name, value in fields.items() if getattr(step, name) != value}
    if data.depends_on_step_id is not None and data.depends_on_step_id == step.id:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'depends_on_step_id', 'Шаг не может зависеть сам от себя')
    for name, change in changes.items():
        setattr(step, name, change['to'])
    if data.checklist_items is not None:
        db.query(TaskPlanTemplateStepChecklistItem).filter(TaskPlanTemplateStepChecklistItem.step_id == step.id).delete()
        for item_position, title in enumerate(data.checklist_items):
            db.add(TaskPlanTemplateStepChecklistItem(step_id=step.id, title=title, position=item_position))
        changes['checklist_items'] = {'from': None, 'to': data.checklist_items}
    if changes:
        record_event(db, request, auth.user, 'task_plan_template.step_update', entity_type='task_plan_template', entity_id=template.id,
                     summary=f'Шаблон «{template.name}»: изменён шаг «{step.title}»', payload=changes)
        db.commit()
    return template_out(db, template)


@router.delete('/task-plan-template-steps/{step_id}', response_model=TemplateOut, summary='Удалить шаг шаблона')
def delete_step(step_id: int, request: Request, auth: AuthContext = Depends(template_editor), db: Session = Depends(get_db)):
    step = db.get(TaskPlanTemplateStep, step_id)
    if step is None:
        raise not_found()
    template = load_template(db, step.template_id, lock=True)
    title = step.title
    db.execute(
        TaskPlanTemplateStep.__table__.update()
        .where(TaskPlanTemplateStep.depends_on_step_id == step.id)
        .values(depends_on_step_id=None)
    )
    db.delete(step)
    record_event(db, request, auth.user, 'task_plan_template.step_delete', entity_type='task_plan_template', entity_id=template.id,
                 summary=f'Шаблон «{template.name}»: удалён шаг «{title}»', payload={'title': title})
    db.commit()
    return template_out(db, template)


@router.put('/task-plan-templates/{template_id}/steps-order', response_model=TemplateOut, summary='Изменить порядок шагов шаблона')
def reorder_steps(template_id: int, data: StepOrderIn, request: Request, auth: AuthContext = Depends(template_editor), db: Session = Depends(get_db)):
    template = load_template(db, template_id, lock=True)
    steps = {s.id: s for s in db.scalars(select(TaskPlanTemplateStep).where(TaskPlanTemplateStep.template_id == template.id))}
    if set(data.step_ids) != set(steps) or len(data.step_ids) != len(steps):
        raise field_error(ErrorCode.VALIDATION_ERROR, 'step_ids', 'Перечислите все шаги шаблона ровно по одному разу')
    for step in steps.values():
        step.position = -(step.position + 1)
    db.flush()
    for position, step_id in enumerate(data.step_ids):
        steps[step_id].position = position
    record_event(db, request, auth.user, 'task_plan_template.reorder', entity_type='task_plan_template', entity_id=template.id,
                 summary=f'Изменён порядок шагов шаблона «{template.name}»', payload={'step_ids': data.step_ids})
    db.commit()
    return template_out(db, template)


# ---------- preview and generation ----------

@router.post('/task-plan-templates/{template_id}/preview', response_model=PreviewOut, summary='Предпросмотр плана', dependencies=[Depends(any_role)])
def preview_plan(template_id: int, data: PlanRequestIn, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    template = load_template(db, template_id)
    check_university_access(db, auth, data.university_id)
    launch = resolve_plan_links(db, data.university_id, data.launch_id)
    snapshot = snapshot_template(db, template)
    steps = preview_steps(db, snapshot, data.university_id, launch, data.start_date, auth.user.id, data.assignee_overrides)
    return PreviewOut(template_id=template.id, template_name=template.name, steps=[PreviewStepOut(**s) for s in steps])


def run_generation(db, request, actor, template, snapshot, university_id, launch_id, start_date, skip_step_ids, assignee_overrides):
    """Shared by the manual /generate endpoint and automatic generation on Interaction creation.
    Caller is responsible for template.is_active checks, skip_step_ids validation, and commit/events.
    """
    launch = resolve_plan_links(db, university_id, launch_id)
    included = [s for s in snapshot['steps'] if s['id'] not in skip_step_ids]
    resolved = {}
    for step in included:
        override = assignee_overrides.get(str(step['id']))
        if override is not None:
            user = db.get(User, override)
            if user is None or not user.is_active:
                raise field_error(ErrorCode.VALIDATION_ERROR, f'assignee_{step["id"]}', 'Указанный пользователь не найден или неактивен')
            resolved[step['id']] = user.id
            continue
        assignee_id, issue = resolve_assignee(db, step, university_id, launch, actor.id)
        if assignee_id is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, f'assignee_{step["id"]}', f'«{step["title"]}»: {issue}')
        resolved[step['id']] = assignee_id

    run = TaskPlanRun(
        template_id=template.id, template_snapshot=snapshot, university_id=university_id,
        launch_id=launch_id, started_by_user_id=actor.id, start_date=start_date,
    )
    db.add(run)
    db.flush()

    created_tasks = []
    for step in included:
        planned_start = add_offset(start_date, step['start_offset_days'], step['offset_unit'])
        deadline = add_offset(start_date, step['deadline_offset_days'], step['offset_unit']) if step['deadline_offset_days'] is not None else None
        task = Task(
            title=step['title'], description=step['description'], priority=step['priority'],
            deadline=deadline, planned_start=planned_start, creator_id=actor.id,
            university_id=university_id, launch_id=launch_id,
            approval_required=step['approval_required'], origin_plan_run_id=run.id,
            origin_template_step_key=str(step['id']),
        )
        db.add(task)
        db.flush()
        db.add(TaskMember(task_id=task.id, user_id=resolved[step['id']], role='assignee'))
        for item_position, title in enumerate(step['checklist_items']):
            db.add(TaskChecklistItem(task_id=task.id, title=title, position=item_position))
        db.add(TaskEvent(task_id=task.id, event_type='created', actor_user_id=actor.id))
        record_event(db, request, actor, 'task.create', entity_type='task', entity_id=task.id,
                     summary=f'Создана задача «{task.title}» по плану «{template.name}»',
                     payload={'title': task.title, 'university_id': university_id, 'plan_run_id': run.id})
        created_tasks.append(task)
    return run, created_tasks


@router.post('/task-plan-templates/{template_id}/generate', response_model=GenerateOut, status_code=201,
             summary='Создать задачи по плану', dependencies=[Depends(any_role)])
def generate_plan(template_id: int, data: GenerateIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    template = load_template(db, template_id)
    if not template.is_active:
        raise field_error(ErrorCode.VALIDATION_ERROR, 'template_id', 'Шаблон неактивен')
    check_university_access(db, auth, data.university_id)
    snapshot = snapshot_template(db, template)

    steps_by_id = {s['id']: s for s in snapshot['steps']}
    for skip_id in data.skip_step_ids:
        step = steps_by_id.get(skip_id)
        if step is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'skip_step_ids', f'Шаг {skip_id} не найден в шаблоне')
        if not step['is_optional']:
            raise field_error(ErrorCode.VALIDATION_ERROR, 'skip_step_ids', f'Шаг «{step["title"]}» обязателен и не может быть пропущен')

    run, created_tasks = run_generation(
        db, request, auth.user, template, snapshot, data.university_id, data.launch_id,
        data.start_date, data.skip_step_ids, data.assignee_overrides,
    )

    record_event(db, request, auth.user, 'task_plan.generate', entity_type='task_plan_run', entity_id=run.id,
                 summary=f'Запущен план «{template.name}»: создано задач — {len(created_tasks)}',
                 payload={'template_id': template.id, 'university_id': data.university_id, 'task_count': len(created_tasks)})
    db.commit()
    return GenerateOut(run_id=run.id, tasks=[task_out(db, t.id).model_dump(mode='json') for t in created_tasks])


# ---------- runs and progress ----------

def plan_runs_out(db, runs):
    """Batch-loads each run's generated tasks and starter for a page of runs instead of querying per row."""
    run_ids = [r.id for r in runs]
    tasks = db.scalars(select(Task).where(Task.origin_plan_run_id.in_(run_ids))).all() if run_ids else []
    tasks_by_run = {}
    for t in tasks:
        tasks_by_run.setdefault(t.origin_plan_run_id, []).append(t)
    starter_ids = {r.started_by_user_id for r in runs if r.started_by_user_id}
    starters = {u.id: u for u in db.scalars(select(User).where(User.id.in_(starter_ids)))} if starter_ids else {}
    return [
        PlanRunOut(
            id=r.id, template_id=r.template_id, template_name=r.template_snapshot.get('name', ''),
            university_id=r.university_id, launch_id=r.launch_id, start_date=r.start_date,
            started_by=PersonOut.model_validate(starters[r.started_by_user_id]) if r.started_by_user_id in starters else None,
            created_at=r.created_at, progress=compute_progress(tasks_by_run.get(r.id, []), r.template_snapshot),
        )
        for r in runs
    ]


@router.get('/task-plan-runs', response_model=list[PlanRunOut], summary='Запуски планов по вузу')
def list_plan_runs(university_id: int = Query(gt=0), auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    check_university_access(db, auth, university_id)
    runs = db.scalars(select(TaskPlanRun).where(TaskPlanRun.university_id == university_id).order_by(TaskPlanRun.created_at.desc())).all()
    return plan_runs_out(db, runs)


@router.get('/task-plan-runs/{run_id}/progress', response_model=PlanProgressOut, summary='Прогресс плана')
def plan_run_progress(run_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    run = db.get(TaskPlanRun, run_id)
    if run is None:
        raise not_found()
    check_university_access(db, auth, run.university_id)
    tasks = db.scalars(select(Task).where(Task.origin_plan_run_id == run.id)).all()
    return compute_progress(tasks, run.template_snapshot)


# ---------- Interaction tasks grouped by plan category ----------

class LaunchTaskOut(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    deadline: date | None
    assignee: PersonOut | None
    is_optional: bool


class LaunchCategoryOut(BaseModel):
    index: int
    name: str
    tasks: list[LaunchTaskOut]
    unfinished_count: int


class LaunchTasksOut(BaseModel):
    current_category: int
    categories: list[LaunchCategoryOut]
    uncategorized: list[LaunchTaskOut]


@router.get('/launches/{launch_id}/tasks', response_model=LaunchTasksOut, summary='Задачи взаимодействия по категориям плана', dependencies=[Depends(any_role)])
def launch_tasks(launch_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    launch = launch_in_scope(db, auth.user, launch_id)  # 404s if the launch itself isn't in scope
    tasks = db.scalars(
        select(Task)
        .where(Task.launch_id == launch_id, visible_tasks_query(auth.user), Task.archived_at.is_(None))
        .order_by(Task.deadline, Task.id)
    ).all()
    run_ids = {t.origin_plan_run_id for t in tasks if t.origin_plan_run_id is not None}
    runs = {r.id: r for r in db.scalars(select(TaskPlanRun).where(TaskPlanRun.id.in_(run_ids)))} if run_ids else {}

    def snapshot_step(task):
        if task.origin_plan_run_id is None or task.origin_template_step_key is None:
            return None
        run = runs.get(task.origin_plan_run_id)
        if run is None:
            return None
        return next((s for s in run.template_snapshot['steps'] if str(s['id']) == task.origin_template_step_key), None)

    def task_out_small(t, step):
        assignee = next((m for m in t.members if m.role == 'assignee'), None)
        return LaunchTaskOut(
            id=t.id, title=t.title, status=t.status, priority=t.priority, deadline=t.deadline,
            assignee=PersonOut(id=assignee.user_id, full_name=db.get(User, assignee.user_id).full_name) if assignee else None,
            is_optional=bool(step.get('is_optional', False)) if step else False,
        )

    current = stage_group(launch.stage)
    buckets = {i: [] for i in range(5)}
    uncategorized = []
    for t in tasks:
        step = snapshot_step(t)
        cat = step.get('category') if step else None
        buckets.get(cat, uncategorized).append(task_out_small(t, step))

    categories = [
        LaunchCategoryOut(
            index=i, name=STAGE_GROUPS[i], tasks=buckets[i],
            unfinished_count=sum(1 for t in buckets[i] if t.status not in ('completed', 'cancelled')) if i < current else 0,
        )
        for i in range(5)
    ]
    return LaunchTasksOut(current_category=current, categories=categories, uncategorized=uncategorized)
