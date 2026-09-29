"""The university's own email address (the card's «Электронная почта вуза»): every role may set it on a university
it can open; employees write to it from their own mail program. Partner addresses are filled in once."""
from alembic import command
from sqlalchemy import create_engine, select, text

from app.db_migrate import alembic_config
from app.models import AuditEvent, University
from app.sync_partner_universities import PARTNER_EMAILS, PARTNERS, sync_partner_universities
from helpers import database
from test_catalog_api import assign, create_university, head, manager  # noqa: F401 (fixtures)


def test_a_manager_sets_the_email_of_an_assigned_university(head, manager, database_url):  # noqa: F811
    university = create_university(head)
    assert university['email'] == ''
    assign(head, university['id'], manager.user_id)

    response = manager.put(f"/api/v1/universities/{university['id']}/email", json={'email': ' Priem@Vuz.ru '})
    assert response.status_code == 200, response.text
    assert response.json()['email'] == 'Priem@Vuz.ru'
    assert manager.get(f"/api/v1/universities/{university['id']}").json()['email'] == 'Priem@Vuz.ru'
    with database(database_url) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'university.email'))
        assert event.payload == {'email': {'from': '', 'to': 'Priem@Vuz.ru'}}


def test_supervisors_can_set_it_on_any_university_and_clear_it(head):  # noqa: F811
    university = create_university(head)
    assert head.put(f"/api/v1/universities/{university['id']}/email", json={'email': 'info@vuz.ru'}).status_code == 200
    cleared = head.put(f"/api/v1/universities/{university['id']}/email", json={'email': ''})
    assert cleared.status_code == 200
    assert cleared.json()['email'] == ''


def test_a_manager_cannot_set_it_on_a_university_they_cannot_open(head, manager):  # noqa: F811
    other = create_university(head)
    response = manager.put(f"/api/v1/universities/{other['id']}/email", json={'email': 'info@vuz.ru'})
    assert response.status_code == 404
    assert head.get(f"/api/v1/universities/{other['id']}").json()['email'] == ''


def test_the_email_is_validated(head):  # noqa: F811
    university = create_university(head)
    for bad in ('not-an-email', 'a@', '@vuz.ru', 'a b@vuz.ru', 'x' * 250 + '@vuz.ru'):
        response = head.put(f"/api/v1/universities/{university['id']}/email", json={'email': bad})
        assert response.status_code == 422, bad
        assert response.json()['details'][0]['field'] == 'email'


def test_the_partner_roster_carries_the_addresses_the_customer_gave(database_url):
    with database(database_url) as db:
        sync_partner_universities(db, apply=True)
        db.commit()
        emails = dict(db.execute(select(University.name, University.email)).all())
    assert emails['ВолгГТУ'] == 'vstu@vstu.ru'
    assert emails['МФТИ'] == 'mipt@mipt.ru'
    # The owner confirmed spbu@spbu.ru for СПбПУ (2026-09-28), so all ten partners have an address.
    assert emails['СПбПУ'] == 'spbu@spbu.ru'
    assert {name for name, email in emails.items() if email} == set(PARTNER_EMAILS)
    assert set(PARTNER_EMAILS) <= {item.name for item in PARTNERS}


def test_the_sync_fills_an_empty_address_but_keeps_one_someone_typed(database_url):
    with database(database_url) as db:
        sync_partner_universities(db, apply=True)
        db.commit()
        db.scalar(select(University).where(University.name == 'ИТМО')).email = ''
        db.scalar(select(University).where(University.name == 'МФТИ')).email = 'office@mipt.ru'
        db.commit()
        result = sync_partner_universities(db, apply=True)
        db.commit()
        emails = dict(db.execute(select(University.name, University.email)).all())
    assert result['emails_filled'] == 1
    assert emails['ИТМО'] == 'info@itmo.ru'
    assert emails['МФТИ'] == 'office@mipt.ru'


def test_migration_0029_fills_partner_addresses_and_downgrades(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0028')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            for name in ('ИТМО', 'СПбПУ', 'Вуз не из списка'):
                connection.execute(text("insert into universities (name, city, contact) values (:n, 'Город', '')"), {'n': name})
        command.upgrade(config, '0029')
        with engine.begin() as connection:
            emails = dict(connection.execute(text('select name, email from universities')).all())
        assert emails == {'ИТМО': 'info@itmo.ru', 'СПбПУ': 'spbu@spbu.ru', 'Вуз не из списка': ''}
        command.downgrade(config, '0028')
        command.upgrade(config, '0029')
        with engine.connect() as connection:
            assert connection.execute(text("select email from universities where name = 'ИТМО'")).scalar_one() == 'info@itmo.ru'
    finally:
        engine.dispose()
