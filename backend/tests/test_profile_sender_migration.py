from alembic import command
from sqlalchemy import create_engine, text

from app.db_migrate import alembic_config


def _seed_0024(connection):
    university_id = connection.execute(text(
        "insert into universities (name, city, contact) values ('Вуз', 'Москва', '') returning id"
    )).scalar_one()
    template_id, status_id = connection.execute(text(
        "select template_id, id from workflow_statuses where position = 0 "
        "and template_id = (select id from workflow_templates where is_default)"
    )).one()

    def user(sub, name, active=True):
        return connection.execute(text(
            "insert into users (keycloak_sub, email, full_name, roles, is_active, created_at) "
            "values (:sub, :email, :name, '{crm-user}', :active, now()) returning id"
        ), {'sub': sub, 'email': f'{sub}@x.test', 'name': name, 'active': active}).scalar_one()

    def launch(owner):
        return connection.execute(text(
            "insert into launches (university_id, program, product, owner, students, stage, deadline, "
            "workflow_template_id, status_id) values (:u, 'Python', 'Среда', :owner, 1, 0, '2026-10-01', :t, :s) "
            "returning id"
        ), {'u': university_id, 'owner': owner, 't': template_id, 's': status_id}).scalar_one()

    anna = user('kc-anna', 'Анна Петрова')
    user('kc-ivan-1', 'Иван Иванов')
    user('kc-ivan-2', 'иван иванов')
    user('kc-old', 'Анна Петрова', active=False)
    sender_id = connection.execute(text(
        "insert into email_sender_identities (email_address, display_name, is_active, created_at) "
        "values ('office@uni.test', 'Офис', true, now()) returning id"
    )).scalar_one()
    inactive_sender = connection.execute(text(
        "insert into email_sender_identities (email_address, display_name, is_active, created_at) "
        "values ('old@uni.test', 'Старый', false, now()) returning id"
    )).scalar_one()
    connection.execute(text("update users set email_sender_identity_id = :s where id = :u"), {'s': sender_id, 'u': anna})
    return {
        'anna': anna, 'sender': sender_id, 'inactive_sender': inactive_sender,
        'linked': launch('  анна петрова '), 'ambiguous': launch('Иван Иванов'), 'unmatched': launch('Уволившийся'),
    }


def test_0025_links_unique_owners_and_preserves_senders(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0024')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            ids = _seed_0024(connection)
        command.upgrade(config, '0025')
        with engine.connect() as connection:
            owners = dict(connection.execute(text('select id, owner_user_id from launches')).all())
            texts = dict(connection.execute(text('select id, owner from launches')).all())
            senders = {row.id: row for row in connection.execute(text(
                'select id, owner_user_id, status, is_active from email_sender_identities'))}
            selected = connection.execute(text('select email_sender_identity_id from users where id = :u'),
                                          {'u': ids['anna']}).scalar_one()
            user_row = connection.execute(text(
                'select first_name, middle_name, last_name, timezone, telegram, whatsapp from users where id = :u'),
                {'u': ids['anna']}).one()
            owner_length = connection.execute(text(
                "select character_maximum_length from information_schema.columns "
                "where table_name = 'launches' and column_name = 'owner'")).scalar_one()
    finally:
        engine.dispose()

    assert owners[ids['linked']] == ids['anna']  # the only ACTIVE match; the deactivated namesake is ignored
    assert owners[ids['ambiguous']] is None
    assert owners[ids['unmatched']] is None
    assert texts[ids['linked']] == '  анна петрова '  # backfill never rewrites text
    assert senders[ids['sender']].owner_user_id is None and senders[ids['sender']].status == 'active'
    assert senders[ids['sender']].is_active is True
    assert senders[ids['inactive_sender']].status == 'active' and senders[ids['inactive_sender']].is_active is False
    assert selected == ids['sender']
    assert tuple(user_row) == ('', '', '', 'Europe/Moscow', '', '')
    assert owner_length == 200


def test_0025_downgrade_round_trip(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0025')
    command.downgrade(config, '0024')
    command.upgrade(config, '0025')
