from sqlalchemy import select

from app.models import AuditEvent, Launch, User
from helpers import database, finish_login, login, make_sessions_stale, start_login
from test_reports import create_launch, create_university


def _rename_in_keycloak(keycloak, subject, name):
    for claims in keycloak.refresh_tokens.values():
        if claims['sub'] == subject:
            claims['name'] = name


def test_login_sync_rename_rewrites_linked_launches_only(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    university = create_university(client, 'Вуз каскада')
    linked = create_launch(client, university['id'], owner='Ирина Петрова')['id']
    unlinked = create_launch(client, university['id'], owner='Сторонний Менеджер')['id']

    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Смирнова')

    with database(database_url) as db:
        assert db.get(Launch, linked).owner == 'Ирина Смирнова'
        assert db.get(Launch, unlinked).owner == 'Сторонний Менеджер'
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'user.renamed'))
        assert event.payload == {'from': 'Ирина Петрова', 'to': 'Ирина Смирнова', 'launches': 1}


def test_session_revalidation_rename_runs_the_same_cascade(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    university = create_university(client, 'Вуз проверки сессии')
    linked = create_launch(client, university['id'], owner='Ирина Петрова')['id']
    _rename_in_keycloak(keycloak, 'kc-irina', 'Ирина Смирнова')
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').json()['user']['full_name'] == 'Ирина Смирнова'
    with database(database_url) as db:
        assert db.get(Launch, linked).owner == 'Ирина Смирнова'


def test_unchanged_name_writes_no_rename_event(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'user.renamed')) is None


def test_login_fills_first_and_last_name_from_token(client, keycloak, database_url):
    response = finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-n',
                            name='Олег Сидоров', email='oleg@x.test', given_name='Олег', family_name='Сидоров')
    assert response.status_code == 302
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-n'))
        assert (user.first_name, user.last_name) == ('Олег', 'Сидоров')


def test_token_without_given_name_keeps_saved_names(client, keycloak, database_url):
    finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-n',
                 name='Олег Сидоров', email='oleg@x.test', given_name='Олег', family_name='Сидоров')
    finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-n',
                 name='Олег Сидоров', email='oleg@x.test')
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-n'))
        assert (user.first_name, user.last_name) == ('Олег', 'Сидоров')
