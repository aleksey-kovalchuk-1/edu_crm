import pytest
from sqlalchemy import update

from app.models import EmailSenderIdentity, User
from helpers import database, login

PROFILE = '/api/v1/profile'
UNAVAILABLE = 'Выбранный адрес отправителя недоступен — выберите другой в профиле'


def _sender(database_url, address, *, owner=None, status='active', is_active=True):
    with database(database_url) as db:
        row = EmailSenderIdentity(email_address=address, display_name=address, owner_user_id=owner,
                                  status=status, is_active=is_active)
        db.add(row)
        db.commit()
        return row.id


def _other_user(database_url):
    with database(database_url) as db:
        other = User(keycloak_sub='kc-o', email='o@x.test', full_name='Другой Пользователь', roles=['crm-user'])
        db.add(other)
        db.commit()
        return other.id


def _select(database_url, user_id, sender_id):
    with database(database_url) as db:
        db.execute(update(User).where(User.id == user_id).values(email_sender_identity_id=sender_id))
        db.commit()


def _capture(app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body, **kwargs: sent.append(kwargs)
    return sent


def test_select_shared_active_sender_and_clear_it(client, keycloak, database_url):
    login(client, keycloak)
    sender_id = _sender(database_url, 'office@uni.test')
    response = client.patch(PROFILE, json={'email_sender_identity_id': sender_id})
    assert response.status_code == 200 and response.json()['email_sender_identity_id'] == sender_id
    assert client.patch(PROFILE, json={'email_sender_identity_id': 0}).json()['email_sender_identity_id'] is None


@pytest.mark.parametrize('kwargs', [
    {'status': 'pending_approval'}, {'status': 'awaiting_confirmation'}, {'status': 'rejected'},
    {'is_active': False}, {'owner': 'other'},
])
def test_select_rejects_unusable_sender(client, keycloak, database_url, kwargs):
    login(client, keycloak)
    if kwargs.get('owner') == 'other':
        kwargs = {'owner': _other_user(database_url)}
    sender_id = _sender(database_url, 'x@uni.test', **kwargs)
    response = client.patch(PROFILE, json={'email_sender_identity_id': sender_id})
    assert response.status_code == 409
    assert response.json()['message'] == UNAVAILABLE


def test_select_unknown_sender_is_rejected(client, keycloak):
    login(client, keycloak)
    assert client.patch(PROFILE, json={'email_sender_identity_id': 999999}).status_code == 409


def test_test_send_refuses_a_sender_deactivated_after_selection(client, keycloak, database_url, app):
    sent = _capture(app)
    login(client, keycloak)
    sender_id = _sender(database_url, 'office@uni.test')
    client.patch(PROFILE, json={'email_sender_identity_id': sender_id})
    with database(database_url) as db:
        db.execute(update(EmailSenderIdentity).where(EmailSenderIdentity.id == sender_id).values(is_active=False))
        db.commit()
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 409 and sent == []
    assert client.get(PROFILE).json()['email_sender_identity_id'] == sender_id  # selection kept, shown as unavailable


def test_test_send_refuses_someone_elses_personal_sender(client, keycloak, database_url, app):
    sent = _capture(app)
    me = login(client, keycloak)
    _select(database_url, me['user']['id'], _sender(database_url, 'p@uni.test', owner=_other_user(database_url)))
    assert client.post('/api/v1/email-senders/test').status_code == 409 and sent == []


def test_test_send_uses_own_active_personal_sender(client, keycloak, database_url, app):
    sent = _capture(app)
    me = login(client, keycloak)
    _select(database_url, me['user']['id'], _sender(database_url, 'mine@uni.test', owner=me['user']['id']))
    assert client.post('/api/v1/email-senders/test').status_code == 200
    assert sent == [{'from_address': 'mine@uni.test', 'from_name': 'mine@uni.test'}]  # display_name of the chosen sender


def test_list_includes_the_selected_sender_even_when_unusable(client, keycloak, database_url):
    me = login(client, keycloak)
    sender_id = _sender(database_url, 'office@uni.test', is_active=False)
    _select(database_url, me['user']['id'], sender_id)
    listed = [s for s in client.get('/api/v1/email-senders').json() if s['id'] == sender_id]
    assert len(listed) == 1 and listed[0]['usable'] is False and listed[0]['is_active'] is False
