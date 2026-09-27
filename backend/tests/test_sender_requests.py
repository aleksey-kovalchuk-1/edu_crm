from datetime import timedelta

from sqlalchemy import select, update

from app.models import AuditEvent, EmailSenderIdentity, User, utcnow
from helpers import database, login

BASE = '/api/v1/email-senders'


def _capture(app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body, **kwargs: sent.append({'to': to, 'body': body, **kwargs})
    return sent


def _token(sent):
    return sent[-1]['body'].split('token=')[1].split()[0]


def _signed_out(client):
    client.cookies.clear()
    client.headers.pop('X-CSRF-Token', None)


def _as(client, keycloak, role, subject, name):
    _signed_out(client)
    return login(client, keycloak, roles=(role,), subject=subject, name=name, email=f'{subject}@x.test')


def _request(client, address='anna@uni-demo.ru'):
    response = client.post(f'{BASE}/requests', json={'email_address': address, 'display_name': 'Анна'})
    assert response.status_code == 201, response.text
    return response.json()


def _approved_token(client, keycloak, app):
    sent = _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ Системы')
    assert client.post(f"{BASE}/{created['id']}/approve").status_code == 200
    return created, sent


def test_full_request_flow_selects_the_confirmed_address(client, keycloak, app, database_url):
    sent = _capture(app)
    anna = _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    assert created['status'] == 'pending_approval' and created['usable'] is False and created['is_shared'] is False

    _as(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    queue = client.get(f'{BASE}/queue').json()
    assert [q['id'] for q in queue] == [created['id']] and queue[0]['requested_by'] == 'Анна Петрова'
    approved = client.post(f"{BASE}/{created['id']}/approve")
    assert approved.status_code == 200 and approved.json()['delivered'] is True
    assert sent[-1]['to'] == 'anna@uni-demo.ru' and '/confirm-sender?token=' in sent[-1]['body']

    _signed_out(client)
    confirmed = client.post(f'{BASE}/confirm', json={'token': _token(sent)})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {'email_address': 'anna@uni-demo.ru'}
    with database(database_url) as db:
        row = db.get(EmailSenderIdentity, created['id'])
        assert row.status == 'active' and row.confirmation_token_hash is None
        assert db.get(User, anna['user']['id']).email_sender_identity_id == created['id']
        actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_type == 'email_sender_identity')))
        assert {'email_sender.request', 'email_sender.approve', 'email_sender.confirm'} <= actions


def test_get_does_not_confirm_and_token_is_single_use(client, keycloak, app):
    created, sent = _approved_token(client, keycloak, app)
    token = _token(sent)
    assert client.get(f'{BASE}/confirm', params={'token': token}).status_code in (404, 405)
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 200
    second = client.post(f'{BASE}/confirm', json={'token': token})
    assert second.status_code == 409 and second.json()['message'] == 'Ссылка недействительна или устарела'


def test_expired_and_wrong_tokens_are_rejected(client, keycloak, app, database_url):
    created, sent = _approved_token(client, keycloak, app)
    token = _token(sent)
    assert client.post(f'{BASE}/confirm', json={'token': 'wrong'}).status_code == 409
    with database(database_url) as db:
        db.execute(update(EmailSenderIdentity).values(confirmation_expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 409


def test_link_after_deactivation_does_not_activate(client, keycloak, app, database_url):
    sent = _capture(app)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ Системы')
    shared = client.post(BASE, json={'email_address': 'office@uni-demo.ru', 'display_name': 'Офис'})
    assert shared.status_code == 201, shared.text
    shared = shared.json()
    assert shared['status'] == 'awaiting_confirmation' and shared['is_shared'] is True
    token = _token(sent)
    assert client.delete(f"{BASE}/{shared['id']}").status_code == 204
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 409
    with database(database_url) as db:
        assert db.get(EmailSenderIdentity, shared['id']).status == 'awaiting_confirmation'


def test_withdrawn_request_link_is_invalid(client, keycloak, app):
    created, sent = _approved_token(client, keycloak, app)
    token = _token(sent)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.delete(f"{BASE}/requests/{created['id']}").status_code == 204
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 409


def test_self_approval_is_forbidden(client, keycloak, app):
    _capture(app)
    _as(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    created = _request(client, 'boss@uni-demo.ru')
    assert client.post(f"{BASE}/{created['id']}/approve").status_code == 403


def test_one_open_request_per_user_and_taken_address(client, keycloak, app):
    _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    _request(client)
    second = client.post(f'{BASE}/requests', json={'email_address': 'other@uni-demo.ru', 'display_name': 'Анна'})
    assert second.status_code == 409
    _as(client, keycloak, 'crm-user', 'kc-ivan', 'Иван Иванов')
    taken = client.post(f'{BASE}/requests', json={'email_address': 'anna@uni-demo.ru', 'display_name': 'Иван'})
    assert taken.status_code == 422


def test_reject_with_reason_and_rerequest_reuses_row(client, keycloak, app):
    _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ Системы')
    assert client.post(f"{BASE}/{created['id']}/reject", json={'reason': 'Не наш домен'}).status_code == 204
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    mine = [s for s in client.get(BASE).json() if s['id'] == created['id']][0]
    assert mine['status'] == 'rejected' and mine['rejection_reason'] == 'Не наш домен'
    again = _request(client)
    assert again['id'] == created['id'] and again['status'] == 'pending_approval' and again['rejection_reason'] == ''


def test_queue_is_for_supervisor_and_admin_only(client, keycloak):
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.get(f'{BASE}/queue').status_code == 403
    assert client.post(f'{BASE}/1/approve').status_code == 403


def test_resend_cooldown_and_new_link_invalidates_old(client, keycloak, app, database_url):
    created, sent = _approved_token(client, keycloak, app)
    first = _token(sent)
    assert client.post(f"{BASE}/{created['id']}/resend").status_code == 429
    with database(database_url) as db:
        db.execute(update(EmailSenderIdentity).values(confirmation_sent_at=utcnow() - timedelta(seconds=61)))
        db.commit()
    assert client.post(f"{BASE}/{created['id']}/resend").status_code == 200
    second = _token(sent)
    assert client.post(f'{BASE}/confirm', json={'token': first}).status_code == 409
    assert client.post(f'{BASE}/confirm', json={'token': second}).status_code == 200


def test_approve_without_provider_says_logged_only(client, keycloak):
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ Системы')
    body = client.post(f"{BASE}/{created['id']}/approve").json()
    assert body['delivered'] is False and 'журнал' in body['message']


def test_list_shows_shared_active_and_own_rows_only(client, keycloak, app, database_url):
    _capture(app)
    with database(database_url) as db:
        db.add(EmailSenderIdentity(email_address='office@uni-demo.ru', display_name='Офис', status='active'))
        db.add(EmailSenderIdentity(email_address='new@uni-demo.ru', display_name='Новый', status='awaiting_confirmation'))
        db.commit()
    _as(client, keycloak, 'crm-user', 'kc-ivan', 'Иван Иванов')
    _request(client, 'ivan@uni-demo.ru')
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    _request(client, 'anna@uni-demo.ru')
    assert {s['email_address'] for s in client.get(BASE).json()} == {'office@uni-demo.ru', 'anna@uni-demo.ru'}
