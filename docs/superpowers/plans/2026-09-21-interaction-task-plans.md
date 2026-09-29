# Interaction-Linked Task Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a new Interaction (`Launch`) is created for a university, automatically generate the standard 14-step onboarding task plan exactly once, linked to both the university and that Interaction; show those tasks on the Interaction page grouped into the same five categories already used to group Interactions themselves, with earlier-category incompletion clearly visible regardless of the Interaction's current stage.

**Architecture:** Reuse the existing `POST /task-plan-templates/{id}/generate` machinery (already creates tasks with `university_id`+`launch_id`, snapshots the template so later edits never rewrite past runs) by extracting its core into a plain function callable both from that endpoint and from a new hook in `POST /api/v1/launches`. Add a persisted `category` (0-4) on each template step, frozen into the run's snapshot exactly like `is_optional`/`priority` already are — not derived from position, since the template's steps are editable and positions can shift. A new `GET /api/v1/launches/{id}/tasks` endpoint computes each task's category by looking up its `origin_template_step_key` in its run's snapshot, and computes the Interaction's *current* category with a new backend port of the frontend's `stageGroup()` (today that function only exists client-side, for grouping Interactions on the board — the same rule needs a server-side source of truth for this new use). Manually-created tasks (no `origin_plan_run_id`) get no category and appear in a separate "Без категории" bucket, never guessed into one of the five.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (backend/app/plan_routes.py, main.py, models.py, workflows.py), React + TypeScript + TanStack Query (frontend/src/pages/LaunchPage.tsx, api/queries.ts).

**Spec:** This plan has no separate spec doc — it was scoped directly in conversation on 2026-09-21 (mapping confirmed against the current codebase before writing this plan; see the confirmation message in that conversation for the research trail).

## Global Constraints

- Changing an Interaction's stage must never re-generate the plan, duplicate tasks, or auto-complete tasks — the stage-change endpoint (`PATCH /api/v1/launches/{id}` in `main.py`) is not touched by this plan at all.
- The optional "revise documents" step (`is_optional=True`, migration 0011) stays optional and skippable exactly as today — nothing in this plan changes step-skipping behavior.
- Never guess a `launch_id` onto an existing task that only has `university_id` set, when that university has more than one Interaction. (Applies to the deferred backfill in Task 6 — there is nothing to backfill in this plan's earlier tasks, since they only handle newly-created Interactions and newly-created manual tasks.)
- Automatic generation must never block Interaction creation: if a step's assignee can't be resolved (no university manager, or several), fall back to the Interaction's creator rather than failing — confirmed with the owner on 2026-09-21 (checked against live data: all 6 current demo universities have zero assigned managers, so this is not a hypothetical edge case).
- Task 6 (the 50-real-universities backfill/preview) is **blocked** — the data doesn't exist yet (owner confirmed 2026-09-21 the spreadsheet is still being prepared). Do not start it until the owner provides the file or says otherwise. An existing 20-university pilot workbook, if one is found anywhere in the repo or elsewhere, is explicitly **not** that file — do not treat it as verified data.
- Locking the University/Interaction fields in `TaskCreateForm` (Task 5) is scoped to that one creation entry point only — it must not make `university_id`/`launch_id` globally immutable on tasks elsewhere, and the backend must keep validating both ids on every write exactly as it already does today (no backend validation is removed or loosened by Task 5).
- No task in this plan deploys anything. The public Cloudflare Tunnel deployment (`compose.public.yaml`, a separate, already-completed piece of work) is out of scope here — do not rebuild or restart the public-facing stack, and do not touch `unicrm.tech`, as part of this plan.
- Do not stage or commit the untracked `.claude/launch.json` (or anything else under `.claude/`) — it is unrelated to this work.

---

### Task 1: `category` on template steps + `is_default_plan` on templates

**Files:**
- Modify: `backend/app/models.py` (`TaskPlanTemplateStep` around line 211, `TaskPlanTemplate` around line 199)
- Create: `backend/migrations/versions/0014_plan_step_categories.py`
- Modify: `backend/app/plan_routes.py` (`TemplateStepOut`/`TemplateStepIn`/`TemplateStepAddIn`/`TemplateStepPatchIn` schemas ~line 65-160, `step_out()`, `snapshot_template()` ~line 209-230, `add_step`/`update_step` handlers)
- Test: `backend/tests/test_plan_templates.py`

**Interfaces:**
- Produces: `TaskPlanTemplateStep.category: int | None` (0-4, matching `frontend/src/lib/format.ts`'s `stageGroups` index — 0=«Первый контакт», 1=«Документы», 2=«Внедрение», 3=«Обучение», 4=«Сопровождение»); `TaskPlanTemplate.is_default_plan: bool`; a snapshot dict that now includes `'category'` per step. Task 2 reads `is_default_plan` to find which template to auto-run; Task 4 reads a run's snapshot `category` per step.

- [ ] **Step 1: Add the columns to the models**

In `backend/app/models.py`, add to `TaskPlanTemplateStep` (after `is_optional`, before `depends_on_step_id`):
```python
    category: Mapped[int | None] = mapped_column(SmallInteger, CheckConstraint('category >= 0 and category <= 4'))
```
and to `TaskPlanTemplate` (after `is_active`):
```python
    is_default_plan: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
```
Check `SmallInteger` is already imported in `models.py` (grep for it — `CheckConstraint`, `Boolean`, `false()` already are, per the surrounding column definitions).

- [ ] **Step 2: Write the migration**

`backend/migrations/versions/0014_plan_step_categories.py` — add both columns, populate the 14 existing steps of `'Адаптация нового вуза'` by title (not position, in case position ever shifts), and mark that template `is_default_plan=True`:

```python
"""plan step categories and default-plan flag

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-21

Adds TaskPlanTemplateStep.category (0-4, matching the five board groups already used for
Interactions — see frontend/src/lib/format.ts stageGroups) and TaskPlanTemplate.is_default_plan
(mirrors WorkflowTemplate.is_default), then backfills both for the one template that exists today.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATE_NAME = 'Адаптация нового вуза'

# title -> category (0=Первый контакт, 1=Документы, 2=Внедрение, 3=Обучение, 4=Сопровождение)
STEP_CATEGORIES = {
    'Найти ответственного контактного лица в вузе': 0,
    'Уточнить актуальность ИТ-программ': 0,
    'Организовать встречу с представителями вуза': 0,
    'Обменяться необходимыми документами': 1,
    'Доработать документы при необходимости': 1,
    'Подписать документы': 1,
    'Передать учебные материалы, лицензии и документацию': 2,
    'Сопроводить внедрение продукта': 2,
    'Обучить преподавателей вуза': 3,
    'Актуализировать учебную программу': 3,
    'Провести занятия': 3,
    'Обновить документацию и учебные материалы': 4,
    'Организовать повышение квалификации преподавателей': 4,
    'Проконтролировать выполнение этапов': 4,
}


def upgrade() -> None:
    op.add_column('task_plan_template_steps', sa.Column('category', sa.SmallInteger(), nullable=True))
    op.create_check_constraint('category_range', 'task_plan_template_steps', 'category >= 0 and category <= 4')
    op.add_column('task_plan_templates', sa.Column('is_default_plan', sa.Boolean(), nullable=False, server_default=sa.false()))

    connection = op.get_bind()
    connection.execute(sa.text(
        'update task_plan_templates set is_default_plan = true where name = :name'
    ), {'name': TEMPLATE_NAME})
    for title, category in STEP_CATEGORIES.items():
        connection.execute(sa.text("""
            update task_plan_template_steps s
            set category = :category
            from task_plan_templates t
            where s.template_id = t.id and t.name = :name and s.title = :title
        """), {'category': category, 'title': title, 'name': TEMPLATE_NAME})


def downgrade() -> None:
    op.drop_column('task_plan_templates', 'is_default_plan')
    op.drop_constraint('category_range', 'task_plan_template_steps', type_='check')
    op.drop_column('task_plan_template_steps', 'category')
```

- [ ] **Step 3: Run the migration and check it**

```bash
cd backend
alembic upgrade head
alembic check
```
Expected: `No new upgrade operations detected` (models and migration agree), and a quick manual check:
```bash
docker compose exec -T db psql -U crm -d edu_crm -c "select title, category from task_plan_template_steps order by position;"
```
Expected: 14 rows, categories `0,0,0,1,1,1,2,2,3,3,3,4,4,4` in position order.

- [ ] **Step 4: Thread `category` through the schemas and snapshot**

In `backend/app/plan_routes.py`:
- `TemplateStepOut`: add `category: int | None`
- `TemplateStepIn` and `TemplateStepAddIn`: add `category: int | None = Field(default=None, ge=0, le=4)`
- `TemplateStepPatchIn`: add `category: int | None = Field(default=None, ge=0, le=4)` (same nullable-optional pattern as `deadline_offset_days`)
- `step_out()`: add `category=step.category` to the constructed `TemplateStepOut`
- `create_template`'s step-insertion loop and `add_step()`: pass `category=data.category` into the new `TaskPlanTemplateStep(...)` construction
- `update_step()`: include `category` in whichever fields it copies from `TemplateStepPatchIn` onto the existing row (follow the same pattern already used for `is_optional`)
- `snapshot_template()`: add `'category': s.category,` to the per-step dict (~line 224)

- [ ] **Step 5: Write the failing test**

Add to `backend/tests/test_plan_templates.py`:
```python
def test_default_plan_template_has_categorized_steps(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    response = client.get('/api/v1/task-plan-templates')
    assert response.status_code == 200
    template = next(t for t in response.json() if t['name'] == 'Адаптация нового вуза')
    categories = [s['category'] for s in template['steps']]
    assert categories == [0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4]


def test_generate_snapshot_includes_step_category(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    user = login(client, keycloak, roles=('crm-user',))
    assign_manager(client, university['id'], user['id'])
    template = create_template(client, steps=[
        {'title': 'Шаг', 'assignee_rule': 'university_manager', 'category': 2,
         'start_offset_days': 0, 'deadline_offset_days': 2, 'offset_unit': 'calendar'},
    ])
    response = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': str(date.today()),
    })
    assert response.status_code == 201, response.text
    from app.db import SessionLocal  # or however tests get a session — match the file's existing pattern
    # (see other tests in this file for the exact db-session fixture already used, e.g. `database_url`)
```
Note: match whichever exact DB-inspection pattern the surrounding tests in this file already use for reading `TaskPlanRun.template_snapshot` directly (several existing tests, e.g. `test_generate_creates_tasks_transactionally_and_stores_snapshot`, already do this — copy that pattern rather than inventing a new one).

- [ ] **Step 6: Run tests, confirm both fail for the right reason (field doesn't exist yet), then confirm pass after Steps 1-4**

```bash
cd backend && .venv/bin/python -m pytest tests/test_plan_templates.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/migrations/versions/0014_plan_step_categories.py backend/app/plan_routes.py backend/tests/test_plan_templates.py
git commit -m "feat(plans): add category to template steps and is_default_plan flag"
```

---

### Task 2: Automatic one-time generation on Interaction creation

**Files:**
- Modify: `backend/app/plan_routes.py` (extract generation core into a reusable function, ~line 537-596)
- Modify: `backend/app/main.py` (`add_launch`, ~line 107-121)
- Test: `backend/tests/test_plan_templates.py`, `backend/tests/test_launches.py` (or wherever launch-creation tests live — grep first)

**Interfaces:**
- Consumes: `TaskPlanTemplate.is_default_plan` (Task 1).
- Produces: `run_generation(db, request, auth_user_id, template, university_id, launch_id, start_date, skip_step_ids, assignee_overrides)` — a plain function (no `AuthContext`/HTTP dependency) that both `generate_plan()` and the new launch hook call, returning the created `TaskPlanRun` and task list. Task 4 relies on every auto-generated task having `origin_plan_run_id` set, exactly as manual generation already guarantees.

- [ ] **Step 1: Extract the generation core out of the `generate_plan` endpoint**

In `backend/app/plan_routes.py`, pull the body of `generate_plan()` (from `snapshot = snapshot_template(...)` through building `created_tasks`, *not* including the `record_event`/`db.commit()` calls at the very end or the endpoint's own validation of `template.is_active`/`skip_step_ids`) into a new function:

```python
def run_generation(db, request, actor_user_id, template, snapshot, university_id, launch_id, start_date, skip_step_ids, assignee_overrides):
    """Shared by the manual /generate endpoint and automatic generation on Interaction creation.
    Caller is responsible for template.is_active checks, skip_step_ids validation, and commit/events."""
    launch = resolve_plan_links(db, university_id, launch_id)
    steps_by_id = {s['id']: s for s in snapshot['steps']}
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
        assignee_id, issue = resolve_assignee(db, step, university_id, launch, actor_user_id)
        if assignee_id is None:
            raise field_error(ErrorCode.VALIDATION_ERROR, f'assignee_{step["id"]}', f'«{step["title"]}»: {issue}')
        resolved[step['id']] = assignee_id

    run = TaskPlanRun(
        template_id=template.id, template_snapshot=snapshot, university_id=university_id,
        launch_id=launch_id, started_by_user_id=actor_user_id, start_date=start_date,
    )
    db.add(run)
    db.flush()

    created_tasks = []
    for step in included:
        planned_start = add_offset(start_date, step['start_offset_days'], step['offset_unit'])
        deadline = add_offset(start_date, step['deadline_offset_days'], step['offset_unit']) if step['deadline_offset_days'] is not None else None
        task = Task(
            title=step['title'], description=step['description'], priority=step['priority'],
            deadline=deadline, planned_start=planned_start, creator_id=actor_user_id,
            university_id=university_id, launch_id=launch_id,
            approval_required=step['approval_required'], origin_plan_run_id=run.id,
            origin_template_step_key=str(step['id']),
        )
        db.add(task)
        db.flush()
        db.add(TaskMember(task_id=task.id, user_id=resolved[step['id']], role='assignee'))
        for item_position, title in enumerate(step['checklist_items']):
            db.add(TaskChecklistItem(task_id=task.id, title=title, position=item_position))
        db.add(TaskEvent(task_id=task.id, event_type='created', actor_user_id=actor_user_id))
        if request is not None:
            record_event(db, request, None, 'task.create', entity_type='task', entity_id=task.id,
                         summary=f'Создана задача «{task.title}» по плану «{template.name}»',
                         payload={'title': task.title, 'university_id': university_id, 'plan_run_id': run.id},
                         actor_user_id=actor_user_id)
        created_tasks.append(task)
    return run, created_tasks
```
Check `record_event`'s actual signature first (grep `def record_event` in `backend/app/audit.py`) — the sketch above assumes it can take an explicit `actor_user_id` distinct from a full `User` object; adjust the call to match whatever it actually accepts (it may already take a `User` row, in which case pass `db.get(User, actor_user_id)`).

Update `generate_plan()` to call `run_generation(...)` and keep its own `record_event('task_plan.generate', ...)` + `db.commit()` + response building afterward, so its behavior (and every existing test in `test_plan_templates.py`) stays identical.

- [ ] **Step 2: Run the full existing plan-template suite to confirm the refactor changed nothing**

```bash
cd backend && .venv/bin/python -m pytest tests/test_plan_templates.py -v
```
Expected: every test that passed before Task 2 still passes, unchanged.

- [ ] **Step 3: Write the failing test for automatic generation**

In `backend/tests/test_plan_templates.py` (or a new `test_launch_auto_plan.py` if launch-creation tests live in a different file — check `grep -rl "post('/api/v1/launches'" backend/tests/` first and follow that file's fixtures):

```python
def test_creating_a_launch_generates_the_default_plan_once(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'deadline': str(date.today() + timedelta(days=90)),
    })
    assert response.status_code == 201, response.text
    launch_id = response.json()['id']

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    engine = create_engine(database_url)
    with Session(engine) as db:
        runs = db.query(TaskPlanRun).filter(TaskPlanRun.launch_id == launch_id).all()
        assert len(runs) == 1
        tasks = db.query(Task).filter(Task.launch_id == launch_id, Task.university_id == university['id']).all()
        assert len(tasks) == 14


def test_launch_creation_falls_back_to_creator_when_no_university_manager(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)  # deliberately no manager assigned
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'deadline': str(date.today() + timedelta(days=90)),
    })
    assert response.status_code == 201, response.text
    # generation must not have failed or been skipped — same 14-task assertion as above
    ...  # assert on assignee: every generated task's assignee is the creator, per db query


def test_launch_creation_does_not_duplicate_the_plan(client, keycloak, database_url):
    # Simulates the one scenario this feature could double-generate in: calling the underlying
    # generation guard twice for the same launch_id. Directly exercises whatever idempotency
    # check Step 4 below adds (e.g. calling the launch-creation hook function twice, or re-POSTing
    # to a retried request path) — write this against the actual guard once Step 4 is implemented.
    ...
```
Fill in the `...` placeholders with real assertions once Step 4's exact guard mechanism is decided (see Step 4) — do not leave them as ellipses in the final code.

- [ ] **Step 4: Add the automatic-generation hook in `add_launch`**

In `backend/app/main.py`, after `db.flush()` for the new `Launch` row and its `StageEvent`/`StatusChange`, before the final `record_event('launch.create', ...)`/`db.commit()`:

```python
from .plan_routes import resolve_assignee, run_generation, snapshot_template
from .models import TaskPlanRun, TaskPlanTemplate

...
    default_plan = db.scalar(select(TaskPlanTemplate).where(TaskPlanTemplate.is_default_plan.is_(True), TaskPlanTemplate.is_active.is_(True)))
    if default_plan is not None:
        snapshot = snapshot_template(db, default_plan)
        overrides = {}
        for step in snapshot['steps']:
            assignee_id, issue = resolve_assignee(db, step, university.id, record, auth.user.id)
            if assignee_id is None:
                overrides[str(step['id'])] = auth.user.id  # fall back to the Interaction's creator
        run_generation(db, request, auth.user.id, default_plan, snapshot, university.id, record.id, date.today(), [], overrides)
```
This runs in the same transaction as the Launch itself (same `db`, one `db.commit()` at the end of `add_launch`) — Launch and its plan either both commit or both roll back. If `default_plan is None` (template missing/deactivated — a configuration issue, not a per-launch one), the Launch is still created with no plan; nothing here should ever raise for a per-launch reason, since every assignee gap now has a fallback.

- [ ] **Step 5: Idempotency guard (duplicate prevention)**

Add, right before generating: skip if a run already exists for this exact `launch_id` (defensive — this hook only runs once per creation today, but the explicit check is what Step 3's "does not duplicate" test exercises, and protects against a future code path calling this twice):
```python
    already_generated = db.scalar(select(TaskPlanRun.id).where(TaskPlanRun.launch_id == record.id))
    if default_plan is not None and already_generated is None:
        ...  # the block from Step 4
```

- [ ] **Step 6: Fill in and run the tests from Step 3**

```bash
cd backend && .venv/bin/python -m pytest tests/test_plan_templates.py tests/test_launches.py -v  # adjust filename per Step 3's finding
```

- [ ] **Step 7: Run the full backend suite**

```bash
cd backend && .venv/bin/python -m pytest -q
```
Expected: all pass, including every pre-existing launch-creation test (a `Launch` row's shape/response is unchanged by this task).

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/app/plan_routes.py backend/tests/
git commit -m "feat(plans): auto-generate the default task plan once on Interaction creation"
```

---

### Task 3: Backend endpoint for an Interaction's categorized tasks

**Owner-mandated revision (2026-09-21), read before implementing:** the endpoint must apply the
*existing* task-visibility policy (`app/task_policy.py`'s `visible_tasks_query()`), not just check
whether the viewer can see the Launch itself — those are two different, already-existing rules in
this codebase (Launches are scoped to a university's assigned managers via `university_scope`;
individual tasks are scoped to creator/assignee/participant/observer/university-manager via
`visible_tasks_query`). Viewing an Interaction must not leak a task the viewer isn't otherwise
allowed to view. `is_optional` must also come from the plan snapshot, not a hardcoded `False`.

**Files:**
- Modify: `backend/app/workflows.py` (port `stageGroup`)
- Modify: `backend/app/plan_routes.py` (new endpoint; it already imports `Launch`, `Task`, `TaskPlanRun`, `User`, `PersonOut` — check for an import cycle bringing in `task_policy.py` before assuming there is or isn't one)
- Test: `backend/tests/test_plan_templates.py`

**Interfaces:**
- Consumes: `app/task_policy.py`'s `visible_tasks_query(user)` (already used identically in `task_routes.py:849`) and `app/workflows.py`'s `launch_in_scope(db, user, launch_id)` (already used by other launch-detail-adjacent code, raises `AppError(ErrorCode.RECORD_NOT_FOUND)` when the launch itself isn't in the viewer's scope).
- Produces: `GET /api/v1/launches/{launch_id}/tasks` → `{current_category: int, categories: [{index, name, tasks: [...], unfinished_count}], uncategorized: [...]}`. Task 5 (frontend) consumes this exact shape.

- [ ] **Step 1: Port `stageGroup` to the backend**

In `backend/app/workflows.py`, add (mirroring `frontend/src/lib/format.ts` exactly — keep both in sync by hand, same as `NEXT_STATUSES` is already mirrored between frontend/backend with the server as source of truth):
```python
STAGE_GROUPS = ['Первый контакт', 'Документы', 'Внедрение', 'Обучение', 'Сопровождение']


def stage_group(stage):
    if stage < 3:
        return 0
    if stage < 6:
        return 1
    if stage < 8:
        return 2
    if stage < 11:
        return 3
    return 4
```

- [ ] **Step 2: Write the failing tests — grouping/category behavior and permissions**

```python
def test_launch_tasks_endpoint_groups_by_category_and_flags_unfinished_earlier(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    user = login(client, keycloak, roles=('crm-user',))
    assign_manager(client, university['id'], user['id'])
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': user['full_name'], 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['current_category'] == 0  # freshly created launch starts at stage 0
    assert len(body['categories']) == 5
    assert body['categories'][0]['name'] == 'Первый контакт'
    assert sum(len(c['tasks']) for c in body['categories']) == 14
    assert body['uncategorized'] == []
    optional_titles = [t['title'] for c in body['categories'] for t in c['tasks'] if t['is_optional']]
    assert optional_titles == ['Доработать документы при необходимости']


def test_launch_tasks_endpoint_404s_for_a_user_outside_the_university_scope(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    manager = login(client, keycloak, roles=('crm-user',))
    assign_manager(client, university['id'], manager['id'])
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': manager['full_name'], 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    login(client, keycloak, roles=('crm-user',))  # a different crm-user, not a manager of this university
    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 404


def test_launch_tasks_endpoint_hides_a_task_the_viewer_cannot_view(client, keycloak, database_url):
    """A task tied to this launch but with no university_id (so university-scope doesn't grant
    access to it) and created by someone else must not appear for a manager who can see every
    *other* task in the same launch — proves the endpoint applies per-task visibility, not just
    'can this viewer see the launch'."""
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    manager = login(client, keycloak, roles=('crm-user',))
    assign_manager(client, university['id'], manager['id'])
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': manager['full_name'], 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    other_user = login(client, keycloak, roles=('crm-user',))
    hidden = client.post('/api/v1/tasks', json={
        'title': 'Приватная задача', 'launch_id': launch['id'], 'assignee_ids': [other_user['id']],
    }).json()
    # Deliberately leave university_id unset on this one task via a direct DB update, to exercise
    # the one case where launch-level and task-level scope genuinely diverge (see task_policy.py's
    # _in_university_scope: `if task.university_id is None: return False`).
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import Session
    from app.models import Task
    engine = create_engine(database_url)
    with Session(engine) as db:
        db.execute(update(Task).where(Task.id == hidden['id']).values(university_id=None))
        db.commit()

    login(client, keycloak, roles=('crm-user',))  # back to the manager
    client.headers.update({})  # (re-login already swaps the test client's active user — see helpers.login)
    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 200
    all_titles = [t['title'] for c in response.json()['categories'] for t in c['tasks']] + [t['title'] for t in response.json()['uncategorized']]
    assert 'Приватная задача' not in all_titles
```
Check `helpers.login`'s exact re-login mechanics (does calling it again swap the active user on the same `client`, or does it need a fresh client?) against how other multi-user tests in this same file or `test_task_api.py` already do it, and fix the sketch above to match — several existing tests already juggle two users (e.g. anything asserting a 403 from a *different* role).

- [ ] **Step 3: Run the tests, confirm they fail for the right reason (route doesn't exist yet — 404 for all three, but the second one's 404 is coincidentally the *expected* result — check its failure message is "no such route", not accidentally passing)**

```bash
cd backend && .venv/bin/python -m pytest tests/test_plan_templates.py -k launch_tasks -v
```

- [ ] **Step 4: Implement the endpoint**

```python
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
        select(Task).where(Task.launch_id == launch_id, visible_tasks_query(auth.user)).order_by(Task.deadline)
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
            is_optional=bool(step['is_optional']) if step else False,
        )

    current = stage_group(launch.stage)
    buckets = {i: [] for i in range(5)}
    uncategorized = []
    for t in tasks:
        step = snapshot_step(t)
        cat = step['category'] if step else None
        (buckets[cat] if cat is not None else uncategorized).append(task_out_small(t, step))

    categories = [
        LaunchCategoryOut(
            index=i, name=STAGE_GROUPS[i], tasks=buckets[i],
            unfinished_count=sum(1 for t in buckets[i] if t.status not in ('completed', 'cancelled')) if i < current else 0,
        )
        for i in range(5)
    ]
    return LaunchTasksOut(current_category=current, categories=categories, uncategorized=uncategorized)
```
Import `stage_group`, `STAGE_GROUPS`, `launch_in_scope` from `.workflows`; import `visible_tasks_query` from `.task_policy` (check that importing `task_policy` into `plan_routes.py` doesn't create a circular import — `task_policy.py` currently imports from `.models` and `.catalog_routes` only, per the earlier grep, so it should be safe, but verify by actually running the app/tests rather than assuming).

- [ ] **Step 5: Run the tests, confirm all three pass; run the full backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/test_plan_templates.py -v
cd backend && .venv/bin/python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/workflows.py backend/app/plan_routes.py backend/tests/test_plan_templates.py
git commit -m "feat(plans): add GET /launches/{id}/tasks, grouped by category and permission-filtered"
```

---

### Task 4: Interaction page shows the categorized task plan

**Files:**
- Create: `frontend/src/api/launchTasks.ts` (query hook)
- Modify: `frontend/src/pages/LaunchPage.tsx`
- Test: `frontend/src/pages/launch.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/launches/{id}/tasks` (Task 3).
- Produces: a rendered "Связанные задачи" section other tasks in this plan don't need to know about — this is the last task that touches the Interaction page for this feature (Task 6's backfill is separate and deferred).

- [ ] **Step 1: Add the query hook**

`frontend/src/api/launchTasks.ts`:
```typescript
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./client";
import type { TaskPriority, TaskStatus } from "./tasks";

export interface LaunchTask {
  id: number;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  deadline: string | null;
  assignee: { id: number; full_name: string } | null;
  is_optional: boolean;
}

export interface LaunchTaskCategory {
  index: number;
  name: string;
  tasks: LaunchTask[];
  unfinished_count: number;
}

export interface LaunchTasksResponse {
  current_category: number;
  categories: LaunchTaskCategory[];
  uncategorized: LaunchTask[];
}

export const useLaunchTasks = (launchId: number) =>
  useQuery({
    queryKey: ["launches", launchId, "tasks"],
    queryFn: () => apiRequest<LaunchTasksResponse>(`/launches/${launchId}/tasks`),
  });
```
Check `apiRequest`'s actual import path/signature in `frontend/src/api/client.ts` first and match it exactly (other API files, e.g. `frontend/src/api/tasks.ts`, show the real pattern).

- [ ] **Step 2: Write the failing test**

Add to `frontend/src/pages/launch.test.tsx`:
```typescript
it("shows the plan's tasks grouped by category, with unfinished-earlier flagged", async () => {
  mockApi({
    "GET /launches/1/tasks": () => ({
      current_category: 2,
      categories: [
        { index: 0, name: "Первый контакт", tasks: [{ id: 1, title: "Найти контакт", status: "completed", priority: "normal", deadline: "2026-01-01", assignee: null, is_optional: false }], unfinished_count: 0 },
        { index: 1, name: "Документы", tasks: [{ id: 2, title: "Подписать документы", status: "new", priority: "normal", deadline: "2026-01-05", assignee: null, is_optional: false }], unfinished_count: 1 },
        { index: 2, name: "Внедрение", tasks: [], unfinished_count: 0 },
        { index: 3, name: "Обучение", tasks: [], unfinished_count: 0 },
        { index: 4, name: "Сопровождение", tasks: [], unfinished_count: 0 },
      ],
      uncategorized: [],
    }),
  });
  renderApp("/interactions/1");
  await screen.findByRole("heading", { name: "Связанные задачи" });
  expect(await screen.findByText("Документы")).toBeTruthy();
  expect(await screen.findByText(/1 незаверш/)).toBeTruthy();  // unfinished_count badge on an earlier-than-current category
  expect(screen.getByText("Подписать документы")).toBeTruthy();
});
```
Check the actual route path for a launch (`renderApp("/interactions/1")` is a guess — grep `paths.interactions`/the router config in `frontend/src/app/navigation.ts` for the real one) and `mockApi`'s exact endpoint-key convention (other test files show it) before finalizing.

- [ ] **Step 3: Run it, confirm it fails (no such heading yet)**

```bash
cd frontend && npm run test -- --run launch.test.tsx
```

- [ ] **Step 4: Add the section to `LaunchPage.tsx`**

After the existing status timeline section, add:
```tsx
import { useLaunchTasks } from "../api/launchTasks";
...
  const launchTasks = useLaunchTasks(launchId);
...
      {launchTasks.data && (
        <section className="panel">
          <h2>Связанные задачи</h2>
          {launchTasks.data.categories.map((c) => (
            <div key={c.index} className="launch-task-category">
              <h3>
                {c.name}
                {c.index === launchTasks.data!.current_category && <span className="badge">текущий этап</span>}
                {c.unfinished_count > 0 && <span className="badge badge-warning">{c.unfinished_count} незаверш.</span>}
              </h3>
              {c.tasks.length === 0 ? (
                <p className="muted">Нет задач</p>
              ) : (
                <ul>
                  {c.tasks.map((t) => (
                    <li key={t.id}>
                      <Link to={taskPath(t.id)}>{t.title}</Link>
                      {" — "}{TASK_STATUS_LABELS[t.status]}
                      {t.assignee && ` · ${t.assignee.full_name}`}
                      {t.deadline && ` · ${formatDate(t.deadline)}`}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {launchTasks.data.uncategorized.length > 0 && (
            <div className="launch-task-category">
              <h3>Без категории</h3>
              <ul>
                {launchTasks.data.uncategorized.map((t) => (
                  <li key={t.id}><Link to={taskPath(t.id)}>{t.title}</Link></li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
```
Import `taskPath` from `../app/navigation` and `TASK_STATUS_LABELS` from `../api/tasks`. Add matching CSS for `.launch-task-category`/`.badge-warning` in `frontend/src/styles.css`, following whatever `.badge`-style class already exists elsewhere (grep for `.badge` first).

- [ ] **Step 5: Run the test, confirm it passes; run the full frontend suite**

```bash
cd frontend && npm run test -- --run
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/launchTasks.ts frontend/src/pages/LaunchPage.tsx frontend/src/pages/launch.test.tsx frontend/src/styles.css
git commit -m "feat(plans): show an Interaction's linked tasks grouped by category"
```

---

### Task 5: Manual task creation from the Interaction page inherits university + launch

**Files:**
- Modify: `frontend/src/pages/LaunchPage.tsx` (add a "Создать задачу" entry point, or check `Layout.tsx`'s existing create-modal flow first — grep how `TaskCreateForm` is currently opened elsewhere, e.g. from `TasksPage.tsx`, and reuse that pattern rather than inventing a second one)
- Modify: `frontend/src/components/forms/TaskCreateForm.tsx`
- Test: `frontend/src/pages/launch.test.tsx`, `frontend/src/pages/tasks.test.tsx`

**Interfaces:**
- Consumes: `TaskCreateForm`'s existing `initialDeadline` prop pattern (D-205) as the template for adding `initialUniversityId`/`initialLaunchId`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/launch.test.tsx`:
```typescript
it("creating a task from the Interaction page locks it to that university and interaction", async () => {
  const api = mockApi({
    "POST /tasks": (call) => [201, { ...api.data.task, id: 9, ...(call.body as object) }],
  });
  renderApp("/interactions/1");
  fireEvent.click(await screen.findByRole("button", { name: /Создать задачу/ }));
  const dialog = await screen.findByRole("dialog", { name: "Новая задача" });
  fireEvent.change(within(dialog).getByPlaceholderText("Например, собрать документы"), { target: { value: "Ручная задача" } });
  fireEvent.submit(dialog.querySelector("form")!);

  await waitFor(() => expect(api.count("POST", "/tasks")).toBe(1));
  expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({
    title: "Ручная задача", university_id: 1, launch_id: 1,
  });
  // the University/Interaction fields are not editable from this entry point
  expect(within(dialog).queryByRole("combobox", { name: "Учебное заведение" })).toBeNull();
});
```
Adjust the fixture launch/university ids to match whatever `mockApi()`'s default launch fixture actually uses (check `frontend/src/test/utils.tsx`).

- [ ] **Step 2: Run it, confirm it fails**

```bash
cd frontend && npm run test -- --run launch.test.tsx
```

- [ ] **Step 3: Add locked initial props to `TaskCreateForm`**

```tsx
export function TaskCreateForm({
  onCreated, onCancel, initialDeadline, initialUniversityId, initialLaunchId,
}: {
  onCreated: (task: Task) => void;
  onCancel: () => void;
  initialDeadline?: string | null;
  /** When set (e.g. opened from an Interaction page), the University/Interaction fields are
   * pre-filled and locked — a task created from that page always belongs to that Interaction. */
  initialUniversityId?: number;
  initialLaunchId?: number;
}) {
  const [universityId, setUniversityId] = useState(initialUniversityId ? String(initialUniversityId) : "");
  const locked = initialUniversityId !== undefined;
  ...
```
Where the University `<select>` currently renders, branch on `locked`: render the university's name as plain text (matching the read-only pattern already used elsewhere, e.g. `TaskSubtasks.tsx`'s read-only assignee text) instead of a `<select>`, when `locked` is true. Do the same for the Interaction field, pre-selecting `initialLaunchId` and rendering it as text rather than a `<select>` when locked. In `submit()`, when `locked`, send `launch_id: initialLaunchId` directly instead of reading it from form data (the field won't be a form control anymore).

- [ ] **Step 4: Wire up the entry point on `LaunchPage.tsx`**

Follow whatever pattern `TasksPage.tsx`/`Layout.tsx` already use to open `TaskCreateForm` in a `Modal` (grep `TaskCreateForm` usages first — there is exactly one existing call site to copy). Add a "Создать задачу" button to `LaunchPage.tsx`'s header area, opening the same modal with `initialUniversityId={launch.university_id}` and `initialLaunchId={launch.id}`.

- [ ] **Step 5: Run the test, confirm it passes; run the full frontend suite**

```bash
cd frontend && npm run test -- --run
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/LaunchPage.tsx frontend/src/components/forms/TaskCreateForm.tsx frontend/src/pages/launch.test.tsx
git commit -m "feat(plans): tasks created from an Interaction page inherit its university and interaction"
```

---

### Task 6 (BLOCKED — do not start until the owner provides the university data)

**University backfill/import preview.** Owner confirmed on 2026-09-21 that the "50 real universities" spreadsheet is still being prepared and doesn't exist yet. When it's ready:
1. Verify the actual current records (universities, their existing Interactions, existing tasks with `university_id` but no `launch_id`) — do not assume the numbers in this plan's research (6 synthetic universities, 0 with `launch_id`-less university-only tasks) still hold; re-check against whatever database the import targets.
2. Import universities via the existing catalog-upload feature (`docs/design/import.md`, `backend/app/import_routes.py`) — do not hand-write a new import path.
3. Build a dry-run preview (reuse the pattern already in `import_routes.py`'s `PREVIEW_ROWS`/preview endpoint) showing: how many universities would be created vs. already exist, how many would get a Launch + auto-generated plan (Task 2's hook already does this for real, going forward — no separate generation code needed here), and which existing `university_id`-only tasks are skipped because that university already has more than one Interaction (never guess which one they belong to).
4. Get explicit owner approval on the preview numbers before running anything that writes.
5. Confirm idempotency: running the same import twice must not create duplicate universities, launches, or plans (Task 2's launch-creation hook is already one-shot per launch; the import step itself needs its own "already imported this row" guard, likely keyed on university name/external id — design this once the actual file's shape is known, not before).

## Self-Review Notes

- **Spec coverage:** trigger = Interaction creation only (Task 2, not the stage-change endpoint, which this plan never touches) ✓. Link to university+launch (Task 2, reuses existing FK columns) ✓. Grouped display under the five categories (Tasks 3-4) ✓. Sequence/responsible/deadline/completion/overdue visible (Task 4's rendered list — status label, assignee, deadline; "overdue" is derivable client-side from deadline+status the same way the List view already does it, or add it as a field in Task 3 if the plain deadline isn't enough on review). Stage change never regenerates/duplicates/auto-completes (Global Constraints — enforced by never touching the stage-change endpoint). Unfinished-earlier-category visibility (Task 3's `unfinished_count`, Task 4's badge). Optional document step stays optional (untouched — Task 1 only adds a field, doesn't change `is_optional` semantics). Monitoring relevant throughout (the `unfinished_count` badge appears on *every* earlier category any time it's non-zero, not just at the end). Manual task creation inherits university+launch (Task 5). Existing launch-linked tasks appear (Task 3's endpoint queries `Task.launch_id`, not just plan-generated ones). No arbitrary attach when ambiguous (Global Constraints; the only place this could happen — backfill — is Task 6, explicitly blocked). Preview before bulk-create, idempotent, no invented universities (Task 6, deferred).
- **Placeholder scan:** Task 2 Step 3's third test has intentional `...` placeholders flagged with an explicit instruction to fill them in once Step 4's guard exists (this is a genuine ordering dependency — the assertion can't be written correctly before the guard mechanism is chosen — not a lazy omission); every other step has complete, runnable code.
- **Type/name consistency:** `run_generation(...)` signature is the same across Task 2 Step 1 (definition) and Step 4 (call site). `LaunchTasksOut`/`LaunchTask`/`LaunchTaskCategory` (Task 3) match `LaunchTasksResponse`/`LaunchTask`/`LaunchTaskCategory` (Task 4) field names and types exactly. `stage_group`/`STAGE_GROUPS` (Task 3) intentionally mirror the frontend's existing `stageGroup`/`stageGroups` (already in `frontend/src/lib/format.ts`) — same values, kept in sync by hand like `NEXT_STATUSES` already is.
- **Owner revision (2026-09-21):** Task 3 now applies `task_policy.py`'s existing `visible_tasks_query()` to the task query (not just `launch_in_scope()` on the Launch itself) and derives `is_optional` from the run's frozen snapshot instead of hardcoding `False`. Three permission tests added: happy path (manager/admin sees everything), an unrelated user gets 404 (blocked at the Launch level, same as viewing the Interaction page today), and a task with no `university_id` inside an otherwise-visible launch stays hidden from a manager who isn't its creator/member — the one case where Launch-level and Task-level scope genuinely diverge in this codebase.
