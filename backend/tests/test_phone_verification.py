import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.main import create_app
from app.models import AuditEvent, PhoneVerificationCode, User, utcnow
from app.phone import PhoneFormatError, normalize_phone
from app.sms import SmsSendError
from helpers import database, login, make_settings

PHONE_PATH = '/api/v1/profile/phone'
VERIFY_PATH = '/api/v1/profile/phone/verify'
PHONE = '+79991234567'


@pytest.fixture
def sent():
    """Records what would have been sent, without hitting real HTTP or reading log output."""
    calls = []

    def fake_sender(settings, phone, message):
        calls.append({'phone': phone, 'message': message})

    fake_sender.calls = calls
    return fake_sender


@pytest.fixture
def app(database_url, keycloak, sent):
    # Overrides conftest's `app` fixture (adds sms_sender) so tests never depend on real HTTP or logs.
    return create_app(make_settings(database_url), http_client=keycloak.http_client(), sms_sender=sent)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def extract_code(message):
    return re.search(r'\d{6}', message).group()


def latest_code(database_url, user_id):
    with database(database_url) as db:
        return db.scalars(
            select(PhoneVerificationCode)
            .where(PhoneVerificationCode.user_id == user_id)
            .order_by(PhoneVerificationCode.created_at.desc())
        ).first()


# ---------- phone normalization (unit-level, no app needed) ----------

def test_normalize_phone_accepts_the_three_input_formats():
    assert normalize_phone('+79991234567') == PHONE
    assert normalize_phone('89991234567') == PHONE
    assert normalize_phone('79991234567') == PHONE
    # Formatting characters (spaces, parens, dashes) are tolerated around any of the three formats.
    assert normalize_phone('+7 (999) 123-45-67') == PHONE
    assert normalize_phone('8 999 123 45 67') == PHONE


@pytest.mark.parametrize('bad', ['', '12345', '+19991234567', '9991234567', 'not a phone', '+7999123456700', '+7999123456'])
def test_normalize_phone_rejects_anything_else(bad):
    with pytest.raises(PhoneFormatError):
        normalize_phone(bad)


# ---------- request -> verify happy path ----------

def test_request_then_verify_happy_path(client, keycloak, database_url, sent):
    me = login(client, keycloak)

    request = client.post(PHONE_PATH, json={'phone': '+7 999 123-45-67'})
    assert request.status_code == 202, request.text
    assert request.json() == {'expires_in': 300}
    assert len(sent.calls) == 1
    assert sent.calls[0]['phone'] == PHONE
    code = extract_code(sent.calls[0]['message'])

    verify = client.post(VERIFY_PATH, json={'code': code})
    assert verify.status_code == 200, verify.text
    assert verify.json()['phone'] == PHONE
    assert verify.json()['phone_verified_at']

    # /me reflects the new state without a separate fetch.
    me_after = client.get('/api/v1/auth/me').json()
    assert me_after['user']['phone'] == PHONE
    assert me_after['user']['phone_verified_at']

    with database(database_url) as db:
        user = db.get(User, me['user']['id'])
        assert user.phone == PHONE
        assert user.phone_verified_at is not None
    record = latest_code(database_url, me['user']['id'])
    assert record.consumed_at is not None


def test_requires_authentication(client):
    assert client.post(PHONE_PATH, json={'phone': PHONE}).status_code == 401
    assert client.post(VERIFY_PATH, json={'code': '123456'}).status_code == 401


def test_invalid_phone_format_is_rejected_with_field_detail(client, keycloak, sent):
    login(client, keycloak)
    response = client.post(PHONE_PATH, json={'phone': 'not-a-phone'})
    assert response.status_code == 422
    body = response.json()
    assert body['code'] == 'VALIDATION_ERROR'
    assert any(d['field'] == 'phone' for d in body['details'])
    assert sent.calls == []


def test_verify_without_a_pending_code_is_rejected(client, keycloak):
    login(client, keycloak)
    response = client.post(VERIFY_PATH, json={'code': '123456'})
    assert response.status_code == 409


# ---------- wrong code / lockout ----------

def test_wrong_code_increments_attempts_and_fifth_attempt_locks_out_the_code(client, keycloak, database_url, sent):
    me = login(client, keycloak)
    client.post(PHONE_PATH, json={'phone': PHONE})
    code = extract_code(sent.calls[0]['message'])
    wrong = '000000' if code != '000000' else '111111'

    for attempt in range(1, 5):
        response = client.post(VERIFY_PATH, json={'code': wrong})
        assert response.status_code == 422, response.text
        assert latest_code(database_url, me['user']['id']).attempts == attempt

    # 5th wrong attempt: the code becomes permanently locked, not just another 422.
    locked_response = client.post(VERIFY_PATH, json={'code': wrong})
    assert locked_response.status_code == 409, locked_response.text
    record = latest_code(database_url, me['user']['id'])
    assert record.attempts == 5
    assert record.consumed_at is None

    # Even the right code no longer works once locked.
    correct_after_lock = client.post(VERIFY_PATH, json={'code': code})
    assert correct_after_lock.status_code == 409, correct_after_lock.text
    assert latest_code(database_url, me['user']['id']).consumed_at is None


# ---------- expiry ----------

def test_expired_code_is_rejected(client, keycloak, database_url, sent):
    login(client, keycloak)
    client.post(PHONE_PATH, json={'phone': PHONE})
    code = extract_code(sent.calls[0]['message'])
    with database(database_url) as db:
        db.execute(update(PhoneVerificationCode).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()

    response = client.post(VERIFY_PATH, json={'code': code})
    assert response.status_code == 409


# ---------- per-user cooldown ----------

def test_second_request_within_60_seconds_is_rejected(client, keycloak, sent):
    login(client, keycloak)
    first = client.post(PHONE_PATH, json={'phone': PHONE})
    assert first.status_code == 202
    second = client.post(PHONE_PATH, json={'phone': PHONE})
    assert second.status_code == 429
    assert len(sent.calls) == 1


def test_request_is_allowed_again_after_the_cooldown_elapses(client, keycloak, database_url, sent):
    login(client, keycloak)
    client.post(PHONE_PATH, json={'phone': PHONE})
    with database(database_url) as db:
        db.execute(update(PhoneVerificationCode).values(created_at=utcnow() - timedelta(seconds=61)))
        db.commit()

    second = client.post(PHONE_PATH, json={'phone': PHONE})
    assert second.status_code == 202
    assert len(sent.calls) == 2


def test_failed_send_does_not_create_a_cooldown_blocking_row(database_url, keycloak):
    def failing_sender(settings, phone, message):
        raise SmsSendError('simulated provider failure')

    app = create_app(make_settings(database_url), http_client=keycloak.http_client(), sms_sender=failing_sender)
    with TestClient(app) as client:
        login(client, keycloak)
        failed = client.post(PHONE_PATH, json={'phone': PHONE})
        assert failed.status_code == 503, failed.text

        with database(database_url) as db:
            assert db.scalar(select(PhoneVerificationCode)) is None

        # A code that was never sent must not leave the user stuck in a cooldown: swap in a working
        # sender (as if the transient provider failure had passed) and confirm the retry succeeds.
        calls = []
        app.state.sms_sender = lambda settings, phone, message: calls.append(message)
        retry = client.post(PHONE_PATH, json={'phone': PHONE})
        assert retry.status_code == 202, retry.text
        assert len(calls) == 1


# ---------- no cross-user verification (the route takes no user_id; it is always auth.user) ----------

def test_a_user_cannot_verify_using_another_users_pending_code(app, keycloak, sent):
    with TestClient(app) as client_a, TestClient(app) as client_b:
        login(client_a, keycloak, subject='kc-user-a', email='a@example.test', name='Пользователь А')
        login(client_b, keycloak, subject='kc-user-b', email='b@example.test', name='Пользователь Б')

        requested = client_a.post(PHONE_PATH, json={'phone': PHONE})
        assert requested.status_code == 202
        code = extract_code(sent.calls[-1]['message'])

        # User B has no pending code of their own, regardless of what user A's code is.
        cross = client_b.post(VERIFY_PATH, json={'code': code})
        assert cross.status_code == 409

        own = client_a.post(VERIFY_PATH, json={'code': code})
        assert own.status_code == 200


# ---------- audit payloads never contain the raw phone number or code ----------

def test_audit_payloads_never_contain_the_raw_phone_number_or_code(client, keycloak, database_url, sent):
    login(client, keycloak)
    client.post(PHONE_PATH, json={'phone': PHONE})
    code = extract_code(sent.calls[0]['message'])
    client.post(VERIFY_PATH, json={'code': code})

    with database(database_url) as db:
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.action.like('phone.%')).order_by(AuditEvent.id)))
    assert [event.action for event in events] == ['phone.verification_requested', 'phone.verified']
    subscriber_digits = PHONE[2:]  # the 10 digits after +7
    for event in events:
        blob = repr(event.payload) + event.summary
        assert PHONE not in blob
        assert subscriber_digits not in blob
        assert code not in blob
