from alembic import command
from sqlalchemy import create_engine, text

from app.db_migrate import alembic_config


def test_existing_launches_get_default_workflow_and_history(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0007')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            university_id = connection.execute(text("insert into universities (name, city, contact) values ('Вуз', 'Москва', '') returning id")).scalar_one()
            launch_id = connection.execute(text(
                "insert into launches (university_id, program, product, owner, students, stage, deadline) "
                "values (:university_id, 'Python', 'Среда', 'Менеджер', 10, 3, '2026-10-01') returning id"
            ), {'university_id': university_id}).scalar_one()
            for stage, moment in [(0, '2026-01-01T10:00:00Z'), (2, '2026-02-01T10:00:00Z'), (3, '2026-03-01T10:00:00Z')]:
                connection.execute(text('insert into stage_events (launch_id, stage, created_at) values (:launch_id, :stage, :created_at)'),
                                   {'launch_id': launch_id, 'stage': stage, 'created_at': moment})

        command.upgrade(config, '0008')

        with engine.connect() as connection:
            statuses = dict(connection.execute(text('select position, id from workflow_statuses order by position')).all())
            assert len(statuses) == 13
            template = connection.execute(text('select name, is_default from workflow_templates')).one()
            assert template == ('Типовое взаимодействие с вузом', True)
            launch = connection.execute(text('select stage, status_id, workflow_template_id is not null from launches')).one()
            assert launch == (3, statuses[3], True)
            history = connection.execute(text('select from_status_id, to_status_id from status_changes order by created_at')).all()
            assert history == [(None, statuses[0]), (statuses[0], statuses[2]), (statuses[2], statuses[3])]
            assert connection.execute(text('select count(*) from stage_events')).scalar_one() == 3

        # This test deliberately stops at 0008 above to check that one migration's data transform in
        # isolation; continue to head so `check` below reflects the whole chain, not just this step.
        command.upgrade(config, 'head')
    finally:
        engine.dispose()
    command.check(config)
