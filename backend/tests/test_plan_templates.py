from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy import select, update

from app.main import generate_default_plan_for_launch
from app.models import Launch, Task, TaskMember, TaskPlanRun, University, User
from helpers import database, login


def create_university(client, name='Тестовый вуз'):
    return client.post('/api/v1/universities', json={'name': name, 'city': 'Москва', 'contact': ''}).json()


def assign_manager(client, university_id, user_id):
    response = client.put(f'/api/v1/universities/{university_id}/managers', json={'user_ids': [user_id]})
    assert response.status_code == 200, response.text


def simple_template_body(**overrides):
    body = {
        'name': 'Тестовый план',
        'description': '',
        'steps': [
            {
                'title': 'Шаг 1', 'assignee_rule': 'university_manager',
                'start_offset_days': 0, 'deadline_offset_days': 2, 'offset_unit': 'calendar',
                'checklist_items': ['Пункт А', 'Пункт Б'],
            },
            {
                'title': 'Шаг 2', 'assignee_rule': 'university_manager',
                'start_offset_days': 2, 'deadline_offset_days': 4, 'offset_unit': 'calendar',
                'depends_on_position': 0,
            },
            {
                'title': 'Необязательный шаг', 'assignee_rule': 'university_manager', 'is_optional': True,
                'start_offset_days': 4, 'deadline_offset_days': 6, 'offset_unit': 'calendar', 'depends_on_position': 1,
            },
        ],
    }
    body.update(overrides)
    return body


def create_template(client, **overrides):
    response = client.post('/api/v1/task-plan-templates', json=simple_template_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_only_supervisor_and_admin_manage_templates(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/task-plan-templates', json=simple_template_body())
    assert response.status_code == 403


def test_create_template_with_steps_checklist_and_dependency(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    template = create_template(client)
    assert template['name'] == 'Тестовый план'
    assert len(template['steps']) == 3
    step1, step2, optional_step = template['steps']
    assert [i['title'] for i in step1['checklist_items']] == ['Пункт А', 'Пункт Б']
    assert step2['depends_on_step_id'] == step1['id']
    assert optional_step['is_optional'] is True


def test_reorder_and_deactivate_template(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    template = create_template(client)
    ids = [s['id'] for s in template['steps']]
    reordered = client.put(f"/api/v1/task-plan-templates/{template['id']}/steps-order", json={'step_ids': [ids[2], ids[0], ids[1]]})
    assert reordered.status_code == 200, reordered.text
    assert [s['id'] for s in reordered.json()['steps']] == [ids[2], ids[0], ids[1]]

    deactivated = client.patch(f"/api/v1/task-plan-templates/{template['id']}", json={'is_active': False})
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()['is_active'] is False

    active_list = client.get('/api/v1/task-plan-templates').json()
    assert template['id'] not in [t['id'] for t in active_list]
    full_list = client.get('/api/v1/task-plan-templates', params={'include_inactive': 'true'}).json()
    assert template['id'] in [t['id'] for t in full_list]


def test_preview_resolves_university_manager_and_computes_dates(client, keycloak, database_url):
    manager = login(client, keycloak, subject='kc-manager', roles=('crm-user',), name='Менеджер Вуза', email='m@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    assign_manager(client, university['id'], manager['user']['id'])
    template = create_template(client)
    start = date(2026, 10, 5)  # Monday

    preview = client.post(f"/api/v1/task-plan-templates/{template['id']}/preview", json={
        'university_id': university['id'], 'start_date': start.isoformat(),
    })
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body['steps']) == 3
    step1 = body['steps'][0]
    assert step1['assignee']['id'] == manager['user']['id']
    assert step1['assignee_issue'] is None
    assert step1['planned_start'] == start.isoformat()
    assert step1['deadline'] == (start + timedelta(days=2)).isoformat()


def test_preview_flags_missing_assignee_without_a_manager(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    template = create_template(client)

    preview = client.post(f"/api/v1/task-plan-templates/{template['id']}/preview", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()['steps'][0]['assignee'] is None
    assert preview.json()['steps'][0]['assignee_issue']


def test_preview_rejects_launch_from_a_different_university(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university_a = create_university(client, 'Вуз А')
    university_b = create_university(client, 'Вуз Б')
    launch = client.post('/api/v1/launches', json={
        'university_id': university_a['id'], 'program': 'Python', 'product': 'Среда', 'owner': 'Менеджер', 'students': 10, 'deadline': '2026-10-01',
    }).json()
    template = create_template(client)

    preview = client.post(f"/api/v1/task-plan-templates/{template['id']}/preview", json={
        'university_id': university_b['id'], 'launch_id': launch['id'], 'start_date': date.today().isoformat(),
    })
    assert preview.status_code == 422
    assert preview.json()['details'][0]['field'] == 'launch_id'


def test_generate_creates_tasks_transactionally_and_stores_snapshot(client, keycloak, database_url):
    manager = login(client, keycloak, subject='kc-manager', roles=('crm-user',), name='Менеджер Вуза', email='m@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    assign_manager(client, university['id'], manager['user']['id'])
    template = create_template(client)
    start = date(2026, 10, 5)

    generated = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': start.isoformat(),
    })
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert len(body['tasks']) == 3  # includes the optional step by default
    for task in body['tasks']:
        assert task['university']['id'] == university['id']
        assert task['assignees'][0]['id'] == manager['user']['id']
    step1_task = body['tasks'][0]
    assert step1_task['checklist']
    assert {i['title'] for i in step1_task['checklist']} == {'Пункт А', 'Пункт Б'}

    with database(database_url) as db:
        run = db.scalar(select(TaskPlanRun).where(TaskPlanRun.id == body['run_id']))
        assert run.template_snapshot['name'] == 'Тестовый план'
        assert len(run.template_snapshot['steps']) == 3
        tasks = db.scalars(select(Task).where(Task.origin_plan_run_id == run.id)).all()
        assert len(tasks) == 3
        assert all(t.university_id == university['id'] for t in tasks)


def test_generate_can_skip_optional_steps(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    template = create_template(client)
    me = client.get('/api/v1/auth/me').json()['user']

    generated = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'assignee_overrides': {str(s['id']): me['id'] for s in template['steps'][:2]},
        'skip_step_ids': [template['steps'][2]['id']],
    })
    assert generated.status_code == 201, generated.text
    assert len(generated.json()['tasks']) == 2

    required_step_id = template['steps'][0]['id']
    optional_only = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'skip_step_ids': [t['id'] for t in template['steps'] if t['id'] != required_step_id and not t['is_optional']],
    })
    # A required step cannot be skipped.
    assert optional_only.status_code == 422
    assert optional_only.json()['details'][0]['field'] == 'skip_step_ids'


def test_generate_requires_resolved_assignees(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    template = create_template(client)

    missing = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
    })
    assert missing.status_code == 422
    assert missing.json()['details'][0]['field'].startswith('assignee')

    me = client.get('/api/v1/auth/me').json()['user']
    resolved = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'assignee_overrides': {str(s['id']): me['id'] for s in template['steps']},
    })
    assert resolved.status_code == 201, resolved.text


def test_template_edit_after_generation_does_not_change_generated_tasks(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    template = create_template(client)
    me = client.get('/api/v1/auth/me').json()['user']
    generated = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'assignee_overrides': {str(s['id']): me['id'] for s in template['steps']},
    }).json()
    original_title = generated['tasks'][0]['title']

    client.patch(f"/api/v1/task-plan-template-steps/{template['steps'][0]['id']}", json={'title': 'Переименованный шаг'})

    task = client.get(f"/api/v1/tasks/{generated['tasks'][0]['id']}").json()
    assert task['title'] == original_title


def test_plan_progress_reports_totals_and_blocked_steps(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    template = create_template(client)
    me = client.get('/api/v1/auth/me').json()['user']
    generated = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'assignee_overrides': {str(s['id']): me['id'] for s in template['steps']},
    }).json()

    progress = client.get(f"/api/v1/task-plan-runs/{generated['run_id']}/progress").json()
    assert progress['total'] == 3
    assert progress['completed'] == 0
    assert progress['blocked'] == 2  # steps 2 and 3 depend on an uncompleted earlier step

    first_task = generated['tasks'][0]
    assert first_task['checklist'], 'step 1 seeds two checklist items in simple_template_body()'
    started = client.post(f"/api/v1/tasks/{first_task['id']}/status", json={'to_status': 'in_progress', 'version': first_task['version']})
    assert started.status_code == 200, started.text
    for item in first_task['checklist']:
        assert client.patch(f"/api/v1/checklist-items/{item['id']}", json={'is_done': True}).status_code == 200
    task_after = client.get(f"/api/v1/tasks/{first_task['id']}").json()
    completed = client.post(f"/api/v1/tasks/{first_task['id']}/status", json={'to_status': 'completed', 'version': task_after['version']})
    assert completed.status_code == 200, completed.text

    progress_after = client.get(f"/api/v1/task-plan-runs/{generated['run_id']}/progress").json()
    assert progress_after['completed'] == 1
    assert progress_after['blocked'] == 1


def test_university_runs_listing(client, keycloak, database_url):
    """Batch-loaded run tasks/starters (performance pass) must still map to the right run."""
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    template = create_template(client)
    other_template = create_template(client, name='Второй план')
    me = client.get('/api/v1/auth/me').json()['user']
    client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'assignee_overrides': {str(s['id']): me['id'] for s in template['steps']},
    })
    client.post(f"/api/v1/task-plan-templates/{other_template['id']}/generate", json={
        'university_id': university['id'], 'start_date': date.today().isoformat(),
        'assignee_overrides': {str(s['id']): me['id'] for s in other_template['steps']},
    })

    runs = client.get('/api/v1/task-plan-runs', params={'university_id': university['id']}).json()
    assert len(runs) == 2
    by_name = {r['template_name']: r for r in runs}
    assert by_name['Тестовый план']['progress']['total'] == 3
    assert by_name['Второй план']['progress']['total'] == 3
    assert by_name['Тестовый план']['started_by']['id'] == me['id']
    assert by_name['Второй план']['started_by']['id'] == me['id']


def test_default_plan_template_has_categorized_steps(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    response = client.get('/api/v1/task-plan-templates')
    assert response.status_code == 200
    template = next(t for t in response.json() if t['name'] == 'Адаптация нового вуза')
    categories = [s['category'] for s in template['steps']]
    assert categories == [0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4]


def test_generate_snapshot_includes_step_category(client, keycloak, database_url):
    manager = login(client, keycloak, subject='kc-manager-cat', roles=('crm-user',), name='Менеджер Категории', email='catmgr@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    assign_manager(client, university['id'], manager['user']['id'])
    template = create_template(client, steps=[
        {'title': 'Шаг', 'assignee_rule': 'university_manager', 'category': 2,
         'start_offset_days': 0, 'deadline_offset_days': 2, 'offset_unit': 'calendar'},
    ])
    response = client.post(f"/api/v1/task-plan-templates/{template['id']}/generate", json={
        'university_id': university['id'], 'start_date': str(date.today()),
    })
    assert response.status_code == 201, response.text

    with database(database_url) as db:
        run = db.scalar(select(TaskPlanRun).where(TaskPlanRun.id == response.json()['run_id']))
        assert run.template_snapshot['steps'][0]['category'] == 2


def test_creating_a_launch_generates_the_default_plan_once(client, keycloak, database_url):
    manager = login(client, keycloak, subject='kc-manager-launch', roles=('crm-user',), name='Менеджер Запуска', email='launchmgr@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    assign_manager(client, university['id'], manager['user']['id'])
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    })
    assert response.status_code == 201, response.text
    launch_id = response.json()['id']

    with database(database_url) as db:
        runs = db.scalars(select(TaskPlanRun).where(TaskPlanRun.launch_id == launch_id)).all()
        assert len(runs) == 1
        tasks = db.scalars(select(Task).where(Task.launch_id == launch_id, Task.university_id == university['id'])).all()
        assert len(tasks) == 14
        assert all(t.origin_plan_run_id == runs[0].id for t in tasks)


def test_launch_creation_falls_back_to_creator_when_no_university_manager(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-supervisor',))['user']
    university = create_university(client)  # deliberately no manager assigned
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    })
    assert response.status_code == 201, response.text
    launch_id = response.json()['id']

    with database(database_url) as db:
        tasks = db.scalars(select(Task).where(Task.launch_id == launch_id)).all()
        assert len(tasks) == 14  # generation must not have failed or been skipped
        task_ids = [t.id for t in tasks]
        members = db.scalars(select(TaskMember).where(TaskMember.task_id.in_(task_ids), TaskMember.role == 'assignee')).all()
        assert len(members) == 14
        assert all(m.user_id == me['id'] for m in members)  # every step falls back to the Interaction's creator


def test_launch_creation_does_not_duplicate_the_plan(client, keycloak, database_url):
    """Simulates the one scenario this feature could double-generate in: the auto-generation hook
    running twice for the same launch_id. The real endpoint only ever calls the hook once per
    Interaction, so this exercises its idempotency guard directly."""
    me = login(client, keycloak, roles=('crm-supervisor',))['user']
    university = create_university(client)
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    })
    assert response.status_code == 201, response.text
    launch_id = response.json()['id']

    with database(database_url) as db:
        launch = db.get(Launch, launch_id)
        uni = db.get(University, university['id'])
        actor = db.get(User, me['id'])
        generate_default_plan_for_launch(db, None, SimpleNamespace(user=actor), uni, launch)
        db.commit()

        runs = db.scalars(select(TaskPlanRun).where(TaskPlanRun.launch_id == launch_id)).all()
        assert len(runs) == 1
        tasks = db.scalars(select(Task).where(Task.launch_id == launch_id)).all()
        assert len(tasks) == 14


def test_launch_tasks_endpoint_groups_by_category_and_flags_unfinished_earlier(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['current_category'] == 0  # freshly created launch starts at stage 0
    assert len(body['categories']) == 5
    assert [c['name'] for c in body['categories']] == [
        'Первый контакт', 'Документы', 'Внедрение', 'Обучение', 'Сопровождение',
    ]
    assert [c['index'] for c in body['categories']] == [0, 1, 2, 3, 4]
    assert sum(len(c['tasks']) for c in body['categories']) == 14
    assert body['uncategorized'] == []
    # All 14 default-plan tasks fall in category 0 (stage 0, before the launch has progressed) or
    # later categories; unfinished_count is only computed for categories *before* current_category (0),
    # so none of them should count anything as unfinished yet.
    assert all(c['unfinished_count'] == 0 for c in body['categories'])
    optional_titles = [t['title'] for c in body['categories'] for t in c['tasks'] if t['is_optional']]
    assert optional_titles == ['Доработать документы при необходимости']
    categorized_ids = {t['id'] for c in body['categories'] for t in c['tasks']}
    assert len(categorized_ids) == 14  # every task appeared exactly once


def test_launch_tasks_endpoint_404s_for_a_user_outside_the_university_scope(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    manager = login(client, keycloak, subject='kc-scope-manager', roles=('crm-user',), name='Менеджер Области', email='scopemgr@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    assign_manager(client, university['id'], manager['user']['id'])
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': manager['user']['full_name'], 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    client.cookies.clear()
    login(client, keycloak, subject='kc-scope-outsider', roles=('crm-user',), name='Посторонний', email='outsider@demo.local')
    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 404


def test_launch_tasks_endpoint_hides_a_task_the_viewer_cannot_view(client, keycloak, database_url):
    """A task tied to this launch but with no university_id (so university-scope doesn't grant
    access to it) and created by someone else must not appear for a manager who can see every
    *other* task in the same launch — proves the endpoint applies per-task visibility, not just
    'can this viewer see the launch'."""
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    manager = login(client, keycloak, subject='kc-hide-manager', roles=('crm-user',), name='Менеджер Скрытых', email='hidemgr@demo.local')
    client.cookies.clear()
    login(client, keycloak, roles=('crm-supervisor',))
    assign_manager(client, university['id'], manager['user']['id'])
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': manager['user']['full_name'], 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    client.cookies.clear()
    other_user = login(client, keycloak, subject='kc-hide-other', roles=('crm-user',), name='Другой Пользователь', email='hideother@demo.local')
    client.cookies.clear()
    # The task's creator must be in the university's scope (or see-all) to create it with launch_id
    # at all, so use the supervisor as creator — the point under test is the *viewing* manager's
    # visibility, not who created the task.
    login(client, keycloak, roles=('crm-supervisor',))
    hidden = client.post('/api/v1/tasks', json={
        'title': 'Приватная задача', 'launch_id': launch['id'], 'assignee_ids': [other_user['user']['id']],
    }).json()
    # Deliberately leave university_id unset on this one task via a direct DB update, to exercise
    # the one case where launch-level and task-level scope genuinely diverge (see task_policy.py's
    # _in_university_scope: `if task.university_id is None: return False`).
    with database(database_url) as db:
        db.execute(update(Task).where(Task.id == hidden['id']).values(university_id=None))
        db.commit()

    client.cookies.clear()
    login(client, keycloak, subject='kc-hide-manager', roles=('crm-user',), name='Менеджер Скрытых', email='hidemgr@demo.local')  # back to the manager
    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    all_titles = [t['title'] for c in body['categories'] for t in c['tasks']] + [t['title'] for t in body['uncategorized']]
    assert 'Приватная задача' not in all_titles
    # Sanity check: the manager does see the other 14 (visible) tasks from the same launch.
    assert sum(len(c['tasks']) for c in body['categories']) + len(body['uncategorized']) == 14


def test_launch_tasks_endpoint_excludes_archived_tasks(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    with database(database_url) as db:
        tasks = db.scalars(select(Task).where(Task.launch_id == launch['id'])).all()
        assert len(tasks) == 14
        archived_task_id = tasks[0].id

    archive = client.post('/api/v1/tasks/bulk/archive', json={'task_ids': [archived_task_id], 'confirm': True})
    assert archive.status_code == 200, archive.text

    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    all_ids = {t['id'] for c in body['categories'] for t in c['tasks']} | {t['id'] for t in body['uncategorized']}
    assert archived_task_id not in all_ids
    assert len(all_ids) == 13


def test_launch_tasks_endpoint_tolerates_a_snapshot_from_before_categories_existed(client, keycloak, database_url):
    """A TaskPlanRun generated before migration 0014 (which added `category` to template steps)
    has a template_snapshot whose steps have no 'category' or 'is_optional' keys. The endpoint must
    read those defensively (step.get(...)) instead of raising KeyError, and such tasks must land in
    `uncategorized` rather than crash the endpoint."""
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client)
    launch = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Пилот', 'product': 'ИТ-школа',
        'owner': 'Тест Тестов', 'students': 10, 'deadline': str(date.today() + timedelta(days=90)),
    }).json()

    with database(database_url) as db:
        run = db.scalar(select(TaskPlanRun).where(TaskPlanRun.launch_id == launch['id']))
        old_style_snapshot = dict(run.template_snapshot)
        old_style_snapshot['steps'] = [
            {k: v for k, v in step.items() if k not in ('category', 'is_optional')}
            for step in run.template_snapshot['steps']
        ]
        db.execute(
            update(TaskPlanRun).where(TaskPlanRun.id == run.id).values(template_snapshot=old_style_snapshot)
        )
        db.commit()

    response = client.get(f"/api/v1/launches/{launch['id']}/tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    assert all(c['tasks'] == [] for c in body['categories'])
    assert len(body['uncategorized']) == 14
    assert all(t['is_optional'] is False for t in body['uncategorized'])
