from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.models import Notification, University, UniversityManager, User
from app.notifications import FOREVER
from helpers import database
from notification_helpers import ensure_user, sign_in

BASE = '/api/v1/notifications'


def _university(db, name='Вуз ленты'):
    university = University(name=name, city='Москва', contact='')
    db.add(university)
    db.flush()
    return university


def _seed(database_url, user_id, university_id, **extra):
    with database(database_url) as db:
        values = dict(user_id=user_id, event_type='university_assigned', title='Вас назначили ответственным за вуз',
                      body='Вуз ленты', link_type='university', link_id=university_id, university_id=university_id)
        values.update(extra)
        row = Notification(**values)
        db.add(row)
        db.commit()
        return row.id


def _anna_with_university(client, keycloak, database_url):
    anna = sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    with database(database_url) as db:
        university = _university(db)
        db.add(UniversityManager(university_id=university.id, user_id=anna['id']))
        db.commit()
        return anna, university.id


def test_list_and_count_show_only_own_visible_notifications(client, keycloak, database_url):
    anna, university_id = _anna_with_university(client, keycloak, database_url)
    other = ensure_user(database_url, 'kc-ivan', 'Иван Иванов')
    mine = _seed(database_url, anna['id'], university_id)
    _seed(database_url, other, university_id)  # someone else's
    with database(database_url) as db:
        hidden_university = _university(db, 'Скрытый вуз').id
        db.commit()
    _seed(database_url, anna['id'], hidden_university)  # a university Анна cannot see
    items = client.get(BASE).json()
    assert [i['id'] for i in items] == [mine]
    assert items[0]['link'] == {'type': 'university', 'id': university_id, 'path': f'/universities/{university_id}'}
    assert client.get(f'{BASE}/unread-count').json() == {'count': 1}


def test_removal_notice_stays_visible_without_a_link(client, keycloak, database_url):
    anna = sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    with database(database_url) as db:
        gone = _university(db, 'Бывший вуз').id
        db.commit()
    _seed(database_url, anna['id'], gone, event_type='university_unassigned', title='Вас сняли с ответственности за вуз')
    items = client.get(BASE).json()
    assert len(items) == 1 and items[0]['link'] is None


def test_contract_links_point_to_the_university_page(client, keycloak, database_url):
    anna, university_id = _anna_with_university(client, keycloak, database_url)
    _seed(database_url, anna['id'], university_id, event_type='contract_signed', link_type='contract', link_id=77)
    assert client.get(BASE).json()[0]['link']['path'] == f'/universities/{university_id}'


def test_mark_one_and_all_read_and_foreign_is_404(client, keycloak, database_url):
    anna, university_id = _anna_with_university(client, keycloak, database_url)
    first, second = _seed(database_url, anna['id'], university_id), _seed(database_url, anna['id'], university_id)
    foreign = _seed(database_url, ensure_user(database_url, 'kc-ivan', 'Иван Иванов'), university_id)
    assert client.post(f'{BASE}/{first}/read').status_code == 204
    assert client.get(f'{BASE}/unread-count').json() == {'count': 1}
    assert [i['id'] for i in client.get(BASE, params={'unread': 'true'}).json()] == [second]
    assert client.post(f'{BASE}/{foreign}/read').status_code == 404
    assert client.post(f'{BASE}/read-all').status_code == 204
    assert client.get(f'{BASE}/unread-count').json() == {'count': 0}


def test_preferences_show_defaults_and_store_changes(client, keycloak, database_url):
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    body = client.get(f'{BASE}/preferences').json()
    assert [g['key'] for g in body['groups']] == ['universities', 'launches', 'tasks', 'contracts']
    events = {e['key']: e['enabled'] for g in body['groups'] for e in g['events']}
    assert len(events) == 21 and events['task_assigned'] is True and events['contract_signed'] is False
    assert events['university_created'] is True
    assert body['paused_until'] is None
    saved = client.put(f'{BASE}/preferences', json={'preferences': {'contract_signed': True, 'task_assigned': False}})
    assert saved.status_code == 200, saved.text
    events = {e['key']: e['enabled'] for g in saved.json()['groups'] for e in g['events']}
    assert events['contract_signed'] is True and events['task_assigned'] is False
    assert client.put(f'{BASE}/preferences', json={'preferences': {'bogus': True}}).status_code == 422


@pytest.mark.parametrize('duration,hours', [('1h', 1), ('1w', 24 * 7)])
def test_pause_for_a_duration(client, keycloak, duration, hours):
    sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    before = datetime.now(timezone.utc)
    until = datetime.fromisoformat(client.put(f'{BASE}/pause', json={'duration': duration}).json()['paused_until'])
    assert timedelta(hours=hours) - timedelta(minutes=1) < until - before < timedelta(hours=hours) + timedelta(minutes=1)


def test_pause_until_tomorrow_8am_local_forever_and_off(client, keycloak, database_url):
    anna = sign_in(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    client.patch('/api/v1/profile', json={'timezone': 'Asia/Vladivostok'})
    until = datetime.fromisoformat(client.put(f'{BASE}/pause', json={'duration': 'tomorrow'}).json()['paused_until'])
    local = until.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Vladivostok'))
    assert (local.hour, local.minute) == (8, 0) and local.date() > datetime.now(local.tzinfo).date()
    forever = client.put(f'{BASE}/pause', json={'duration': 'forever'}).json()['paused_until']
    assert datetime.fromisoformat(forever) == FOREVER
    assert client.put(f'{BASE}/pause', json={'duration': 'off'}).json()['paused_until'] is None
    assert client.put(f'{BASE}/pause', json={'duration': 'soon'}).status_code == 422


def test_older_visible_notifications_are_not_crowded_out_and_count_matches(client, keycloak, database_url):
    anna, university_id = _anna_with_university(client, keycloak, database_url)
    visible = _seed(database_url, anna['id'], university_id)
    with database(database_url) as db:
        hidden = _university(db, 'Вуз, к которому доступа больше нет').id
        db.add_all([Notification(user_id=anna['id'], event_type='university_contacts_changed', title='t', body='b',
                                 link_type='university', link_id=hidden, university_id=hidden) for _ in range(160)])
        db.commit()
    items = client.get(BASE).json()
    assert [i['id'] for i in items] == [visible]
    assert client.get(f'{BASE}/unread-count').json() == {'count': len(items)}


def test_count_uses_a_fixed_number_of_queries(client, keycloak, database_url, app):
    from sqlalchemy import event
    anna, university_id = _anna_with_university(client, keycloak, database_url)
    for _ in range(30):
        _seed(database_url, anna['id'], university_id)
    statements = []
    engine = app.state.session_factory.kw['bind']
    listener = lambda *args: statements.append(1)  # noqa: E731
    event.listen(engine, 'before_cursor_execute', listener)
    try:
        assert client.get(f'{BASE}/unread-count').json() == {'count': 30}
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
    assert len(statements) < 10  # auth/session queries plus one count, not one query per notification
