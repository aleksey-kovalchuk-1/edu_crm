from datetime import date, timedelta

from sqlalchemy import select

from app.models import Task, TaskPlanRun
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
