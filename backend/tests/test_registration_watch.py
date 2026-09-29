"""New Keycloak sign-ups (owner decisions 2026-09-28/29: sign-up stays in Keycloak). As soon as an account without a
CRM role appears, superadmins get one bell notification and the administrator one e-mail, both saying whether the
address is confirmed yet. The applicant gets one acknowledgement e-mail, but only once they have confirmed their
address (an unconfirmed one may belong to someone else). Disabled and approved accounts are ignored; failures retry."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.email import EmailSendError
from app.main import create_app
from app.models import AuditEvent, OrganizationProfile
from app.registration_watch import ACK_SUBJECT, ADMIN_SUBJECT, acknowledgement_text, admin_alert_text, watch_registrations
from helpers import database, login, make_settings
from notification_helpers import disable, ensure_user, notifications
from test_admin_routes import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET


@pytest.fixture
def configured_app(database_url, keycloak):
    return create_app(
        make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                      keycloak_admin_client_secret=ADMIN_CLIENT_SECRET, keycloak_admin_base_url=ADMIN_BASE_URL),
        http_client=keycloak.http_client(),
    )


class Outbox:
    def __init__(self, failures=0):
        self.sent, self.failures = [], failures

    def __call__(self, to, subject, body):
        if self.failures:
            self.failures -= 1
            raise EmailSendError('provider down')
        self.sent.append((to, subject, body))

    def to(self, address):
        return [(subject, body) for to, subject, body in self.sent if to == address]


def _staff(database_url):
    return {
        'super': ensure_user(database_url, 'kc-super', 'Ирина', roles=('crm-superadmin', 'crm-admin', 'crm-supervisor')),
        'admin': ensure_user(database_url, 'kc-admin', 'Админ', roles=('crm-admin',)),
        'kam': ensure_user(database_url, 'kc-kam', 'КАМ', roles=('crm-user',)),
    }


def _watch(app, outbox, **extra):
    options = {'send': outbox, 'contact_email': 'admin@unicrm.ru', 'email_configured': True,
               'crm_url': 'https://unicrm.tech', **extra}
    return watch_registrations(app.state.session_factory, app.state.keycloak_admin, **options)


def _audit(database_url, action):
    with database(database_url) as db:
        return [(e.entity_type, e.entity_id) for e in db.scalars(select(AuditEvent).where(AuditEvent.action == action))]


def test_an_unconfirmed_sign_up_alerts_superadmins_and_the_administrator_at_once(configured_app, keycloak, database_url):
    staff = _staff(database_url)
    keycloak.add_admin_user(id='kc-new', email='ivanov@edu.hse.ru', username='ivanov', roles=[],
                            first_name='Иван', last_name='Иванов', email_verified=False)
    outbox = Outbox()
    _watch(configured_app, outbox)
    _watch(configured_app, outbox)

    assert notifications(database_url, event_type='registration_pending') == [(staff['super'], 'registration_pending', 'registration', 0)]
    assert outbox.to('admin@unicrm.ru') == [(ADMIN_SUBJECT, admin_alert_text(
        name='Иван Иванов', username='ivanov', email='ivanov@edu.hse.ru', confirmed=False, crm_url='https://unicrm.tech'))]
    # Nothing goes to an address nobody has confirmed yet.
    assert outbox.to('ivanov@edu.hse.ru') == []
    assert _audit(database_url, 'registration.admin_notified') == [('keycloak_user', 'kc-new')]


def test_the_applicant_is_acknowledged_once_after_confirming(configured_app, keycloak, database_url):
    _staff(database_url)
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[], email_verified=False)
    outbox = Outbox()
    _watch(configured_app, outbox)
    keycloak.admin_users['kc-new']['emailVerified'] = True
    _watch(configured_app, outbox)
    _watch(configured_app, outbox)
    assert outbox.to('ivanov@mail.ru') == [(ACK_SUBJECT, acknowledgement_text('admin@unicrm.ru'))]
    assert len(outbox.to('admin@unicrm.ru')) == 1
    assert len(notifications(database_url, event_type='registration_pending')) == 1
    assert _audit(database_url, 'registration.acknowledged') == [('keycloak_user', 'kc-new')]


def test_the_administrator_email_names_the_applicant_and_links_the_queue():
    text = admin_alert_text(name='Иван Иванов', username='ivanov', email='ivanov@mail.ru', confirmed=False,
                            crm_url='https://unicrm.tech')
    assert 'Иван Иванов' in text and 'ivanov' in text and 'ivanov@mail.ru' in text
    assert 'ещё не подтвердил' in text
    assert 'https://unicrm.tech/settings/users' in text
    assert 'подтверждён' in admin_alert_text(name='Иван Иванов', username='ivanov', email='ivanov@mail.ru',
                                             confirmed=True, crm_url='https://unicrm.tech')


def test_the_acknowledgement_is_the_owners_text():
    assert acknowledgement_text('admin@unicrm.ru') == (
        'Администратор получил вашу регистрацию. В ближайшее время он ее рассмотрит. '
        'Если вы уже долго ждете, напишите на почту Администратору: admin@unicrm.ru.'
    )


def test_disabled_and_approved_accounts_are_ignored(configured_app, keycloak, database_url):
    _staff(database_url)
    keycloak.add_admin_user(id='kc-disabled', email='b@mail.ru', username='b', roles=[], enabled=False)
    keycloak.add_admin_user(id='kc-kam', email='c@mail.ru', username='c', roles=['crm-user'])
    outbox = Outbox()
    _watch(configured_app, outbox)
    assert notifications(database_url, event_type='registration_pending') == []
    assert outbox.sent == []


def test_failed_emails_are_retried_on_the_next_pass(configured_app, keycloak, database_url):
    _staff(database_url)
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[])
    outbox = Outbox(failures=2)
    _watch(configured_app, outbox)
    assert outbox.sent == []
    assert len(notifications(database_url, event_type='registration_pending')) == 1
    _watch(configured_app, outbox)
    assert sorted(to for to, _, _ in outbox.sent) == ['admin@unicrm.ru', 'ivanov@mail.ru']
    assert len(notifications(database_url, event_type='registration_pending')) == 1


def test_without_a_real_mail_provider_nothing_is_counted_as_sent(configured_app, keycloak, database_url):
    _staff(database_url)
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[])
    outbox = Outbox()
    _watch(configured_app, outbox, email_configured=False)
    assert outbox.sent == []
    assert len(notifications(database_url, event_type='registration_pending')) == 1
    assert _audit(database_url, 'registration.acknowledged') == []
    assert _audit(database_url, 'registration.admin_notified') == []


def test_the_organisation_email_is_the_fallback_contact(configured_app, keycloak, database_url):
    _staff(database_url)
    with database(database_url) as db:
        profile = db.scalar(select(OrganizationProfile))
        profile.email = 'office@school.ru'
        db.commit()
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[])
    outbox = Outbox()
    _watch(configured_app, outbox, contact_email='')
    assert outbox.to('ivanov@mail.ru') == [(ACK_SUBJECT, acknowledgement_text('office@school.ru'))]
    assert [subject for subject, _ in outbox.to('office@school.ru')] == [ADMIN_SUBJECT]


def test_a_superadmin_who_turned_it_off_gets_no_notification(configured_app, keycloak, database_url):
    staff = _staff(database_url)
    disable(database_url, staff['super'], 'registration_pending')
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[])
    _watch(configured_app, Outbox())
    assert notifications(database_url, event_type='registration_pending') == []


def test_without_admin_credentials_the_pass_does_nothing(app, database_url):
    assert watch_registrations(app.state.session_factory, app.state.keycloak_admin, send=Outbox(),
                               contact_email='x@y.ru', email_configured=True) == {
        'pending': 0, 'notified': 0, 'admin_emailed': 0, 'acknowledged': 0}


def test_only_superadmins_see_the_notification_and_its_settings_group(configured_app, keycloak, database_url):
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[],
                            first_name='Иван', last_name='Иванов', email_verified=False)
    with TestClient(configured_app) as client:
        login(client, keycloak, roles=('crm-superadmin', 'crm-admin', 'crm-supervisor'), subject='kc-super', name='Ирина')
        _watch(configured_app, Outbox())
        items = client.get('/api/v1/notifications').json()
        assert [(i['event_type'], i['title'], i['link']['path']) for i in items] == [
            ('registration_pending', 'Новая заявка на доступ', '/settings/users')]
        assert 'ivanov@mail.ru' in items[0]['body']
        assert 'адрес ещё не подтверждён' in items[0]['body']
        groups = [g['key'] for g in client.get('/api/v1/notifications/preferences').json()['groups']]
        assert 'access' in groups
    with TestClient(configured_app) as client:
        login(client, keycloak, roles=('crm-admin',), subject='kc-admin', name='Админ')
        assert client.get('/api/v1/notifications').json() == []
        groups = [g['key'] for g in client.get('/api/v1/notifications/preferences').json()['groups']]
        assert 'access' not in groups


def test_the_notifier_pass_sends_through_the_configured_mailbox(configured_app, keycloak, database_url):
    from dataclasses import replace

    from app.notification_scheduler import registration_pass
    _staff(database_url)
    keycloak.add_admin_user(id='kc-new', email='ivanov@mail.ru', username='ivanov', roles=[])
    sent = []
    settings = replace(configured_app.state.settings, email_smtp_host='smtp.yandex.ru', public_base_url='https://unicrm.tech',
                       email_sender_address='noreply@school.ru', access_contact_email='admin@school.ru')
    result = registration_pass(configured_app.state.session_factory, settings, configured_app.state.keycloak_admin,
                               sender=lambda s, to, subject, body: sent.append((s.email_smtp_host, to, subject)))
    assert result == {'pending': 1, 'notified': 1, 'admin_emailed': 1, 'acknowledged': 1}
    assert sorted(sent) == [('smtp.yandex.ru', 'admin@school.ru', ADMIN_SUBJECT), ('smtp.yandex.ru', 'ivanov@mail.ru', ACK_SUBJECT)]


def test_the_sign_up_check_runs_every_minute():
    from app.notification_scheduler import INTERVAL_SECONDS, SIGNUP_INTERVAL_SECONDS
    assert SIGNUP_INTERVAL_SECONDS == 60
    assert INTERVAL_SECONDS % SIGNUP_INTERVAL_SECONDS == 0
