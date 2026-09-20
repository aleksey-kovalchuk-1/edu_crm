from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db_migrate import alembic_config


def test_legacy_tasks_get_status_and_matched_owner(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0009')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            university_id = connection.execute(text(
                "insert into universities (name, city, contact) values ('Вуз', 'Москва', '') returning id"
            )).scalar_one()
            template_id, status_id = connection.execute(text(
                "select template_id, id from workflow_statuses where position = 0 "
                "and template_id = (select id from workflow_templates where is_default)"
            )).one()
            launch_id = connection.execute(text(
                "insert into launches (university_id, program, product, owner, students, stage, deadline, "
                "workflow_template_id, status_id) "
                "values (:university_id, 'Python', 'Среда', 'Менеджер', 10, 0, '2026-10-01', :template_id, :status_id) "
                "returning id"
            ), {'university_id': university_id, 'template_id': template_id, 'status_id': status_id}).scalar_one()
            connection.execute(text(
                "insert into users (keycloak_sub, email, full_name, roles, is_active, created_at) "
                "values ('kc-1', 'anna@educrm-demo.ru', 'Анна Демо', '{crm-user}', true, now())"
            ))
            # Done task whose owner matches exactly one active user (by full_name, case/space-insensitive).
            done_id = connection.execute(text(
                "insert into tasks (launch_id, title, owner, deadline, done) "
                "values (:launch_id, 'Собрать документы', '  анна демо  ', '2026-01-15', true) returning id"
            ), {'launch_id': launch_id}).scalar_one()
            # Open task whose owner text matches no user: must be preserved, not matched.
            unmatched_id = connection.execute(text(
                "insert into tasks (launch_id, title, owner, deadline, done) "
                "values (:launch_id, 'Организовать встречу', 'Уволившийся Сотрудник', '2026-11-01', false) returning id"
            ), {'launch_id': launch_id}).scalar_one()

        command.upgrade(config, '0010')

        with engine.connect() as connection:
            done_row = connection.execute(text(
                'select status, priority, creator_id, owner, deadline, launch_id, version '
                'from tasks where id = :id'
            ), {'id': done_id}).one()
            assert done_row.status == 'completed'
            assert done_row.priority == 'normal'
            assert done_row.owner == '  анна демо  '  # untouched, even though matched
            assert done_row.deadline.isoformat() == '2026-01-15'
            assert done_row.launch_id == launch_id
            assert done_row.version == 1
            matched_user_id = connection.execute(text("select id from users where full_name = 'Анна Демо'")).scalar_one()
            assert done_row.creator_id == matched_user_id

            unmatched_row = connection.execute(text(
                'select status, creator_id, owner from tasks where id = :id'
            ), {'id': unmatched_id}).one()
            assert unmatched_row.status == 'new'
            assert unmatched_row.creator_id is None
            assert unmatched_row.owner == 'Уволившийся Сотрудник'

            # New tables exist and are queryable (empty).
            for table in (
                'task_members', 'task_checklist_items', 'task_tags', 'task_tag_links',
                'task_comments', 'task_attachments', 'task_events',
                'task_plan_templates', 'task_plan_template_steps', 'task_plan_template_step_checklist_items',
                'task_plan_runs', 'task_user_preferences',
            ):
                assert connection.execute(text(f'select count(*) from {table}')).scalar_one() == 0

            # launch_id and deadline are now optional for new tasks.
            connection.execute(text(
                "insert into tasks (title, status, priority, version) values ('Задача без вуза', 'new', 'normal', 1)"
            ))

        command.upgrade(config, 'head')
    finally:
        engine.dispose()
    command.check(config)


def test_invalid_status_rejected(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, 'head')
    engine = create_engine(empty_database_url)
    try:
        with engine.connect() as connection:
            try:
                connection.execute(text(
                    "insert into tasks (title, status, priority, version) values ('x', 'bogus', 'normal', 1)"
                ))
                connection.commit()
                assert False, 'expected a check constraint violation'
            except Exception as error:
                assert 'tasks_status_check' in str(error) or 'check constraint' in str(error).lower()
    finally:
        engine.dispose()


NEW_TABLES = (
    'task_members', 'task_checklist_items', 'task_tags', 'task_tag_links',
    'task_comments', 'task_attachments', 'task_events',
    'task_plan_templates', 'task_plan_template_steps', 'task_plan_template_step_checklist_items',
    'task_plan_runs', 'task_user_preferences',
)


def test_downgrade_from_head_restores_the_pre_0010_schema(empty_database_url):
    """0011's downgrade (delete checklist items -> steps -> template) and 0010's downgrade (drop the
    12 new tables and columns) are reversible code paths every other test exercises only via upgrade —
    this is the one test that actually runs them, against a database seeded with real rows, not empty
    tables, so a downgrade that forgets a dependent row (e.g. the 0011 seed template's own steps and
    their checklist items) fails on a real foreign-key violation instead of looking fine on an empty DB."""
    config = alembic_config(empty_database_url)
    command.upgrade(config, 'head')
    engine = create_engine(empty_database_url)
    try:
        with engine.connect() as connection:
            seeded = connection.execute(text('select count(*) from task_plan_templates')).scalar_one()
            assert seeded == 1  # 0011's seed template
            steps = connection.execute(text('select count(*) from task_plan_template_steps')).scalar_one()
            assert steps > 0
            checklist_items = connection.execute(
                text('select count(*) from task_plan_template_step_checklist_items')
            ).scalar_one()
            assert checklist_items > 0
            columns = {c['name'] for c in inspect(engine).get_columns('tasks')}
            assert {'status', 'priority', 'version', 'creator_id', 'archived_at'} <= columns

        command.downgrade(config, '0009')

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        for table in NEW_TABLES:
            assert table not in tables, f'{table} should have been dropped by the downgrade'
        columns = {c['name'] for c in inspector.get_columns('tasks')}
        # The pre-0010 placeholder shape is back: owner/done present, the new columns gone.
        assert {'owner', 'done', 'launch_id', 'title', 'deadline'} <= columns
        assert not {'status', 'priority', 'version', 'creator_id', 'archived_at'} & columns

        # A full round trip (down to the placeholder, back up to head) must also succeed cleanly.
        command.upgrade(config, 'head')
        with engine.connect() as connection:
            assert connection.execute(text('select count(*) from task_plan_templates')).scalar_one() == 1
    finally:
        engine.dispose()
