from alembic import command
from sqlalchemy import select

from app.db_migrate import alembic_config
from app.models import UserSession
from helpers import database, finish_login, start_login


def test_login_stores_the_keycloak_session_id(client, keycloak, database_url):
    response = finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-s', name='Сеанс Тестов',
                            email='s@x.test', sid='kc-session-123')
    assert response.status_code == 302
    with database(database_url) as db:
        assert db.scalar(select(UserSession.keycloak_session_id)) == 'kc-session-123'


def test_login_without_sid_leaves_it_empty(client, keycloak, database_url):
    finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-s', name='Сеанс Тестов', email='s@x.test')
    with database(database_url) as db:
        assert db.scalar(select(UserSession.keycloak_session_id)) is None


def test_migration_round_trip(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0028')
    command.downgrade(config, '0027')
    command.upgrade(config, '0028')
