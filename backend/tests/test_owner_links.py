from app.models import Launch, User
from app.owner_links import match_owner_user
from app.plan_routes import resolve_assignee
from helpers import database, login
from test_reports import create_launch, create_university


def _user(db, sub, name, active=True):
    user = User(keycloak_sub=sub, email=f'{sub}@x.test', full_name=name, roles=['crm-user'], is_active=active)
    db.add(user)
    db.flush()
    return user


def test_match_owner_ignores_case_spaces_and_inactive_namesakes(database_url):
    with database(database_url) as db:
        anna = _user(db, 'kc-a', 'Анна Петрова')
        _user(db, 'kc-old', 'Анна Петрова', active=False)
        _user(db, 'kc-i1', 'Иван Иванов')
        _user(db, 'kc-i2', 'иван иванов')
        assert match_owner_user(db, '  анна   петрова ') == anna.id
        assert match_owner_user(db, 'Иван Иванов') is None
        assert match_owner_user(db, 'Никто') is None
        assert match_owner_user(db, '') is None


def test_created_launch_is_linked_to_the_matching_user(client, keycloak):
    me = login(client, keycloak, roles=('crm-admin',), name='Ирина Петрова')
    university = create_university(client, 'Вуз связи')
    launch = create_launch(client, university['id'], owner=' ирина петрова ')
    assert launch['owner_user_id'] == me['user']['id']
    other = create_launch(client, university['id'], owner='Посторонний человек')
    assert other['owner_user_id'] is None


def test_interaction_owner_step_uses_the_link_before_text(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-admin',), name='Ирина Петрова')
    university = create_university(client, 'Вуз назначения')
    launch_id = create_launch(client, university['id'], owner='Ирина Петрова')['id']
    with database(database_url) as db:
        launch = db.get(Launch, launch_id)
        launch.owner = 'Текст разошёлся с именем'  # drift: only the link can resolve it now
        db.flush()
        step = {'assignee_rule': 'interaction_owner'}
        assert resolve_assignee(db, step, university['id'], launch, None) == (me['user']['id'], None)
        launch.owner_user_id = None
        user_id, issue = resolve_assignee(db, step, university['id'], launch, None)
        assert user_id is None and 'однозначно' in issue
