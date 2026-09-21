import logging

from app.bootstrap_superadmin import bootstrap_superadmin
from app.keycloak_admin import KeycloakAdminClient
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET, FakeKeycloak


def make_client(fake):
    return KeycloakAdminClient(base_url=ADMIN_BASE_URL, client_id=ADMIN_CLIENT_ID, client_secret=ADMIN_CLIENT_SECRET, http_client=fake.http_client())


def test_grants_superadmin_to_the_configured_email_when_none_exists():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='owner@demo.local', username='owner', roles=['crm-admin'])
    client = make_client(fake)
    bootstrap_superadmin(client, email='owner@demo.local')
    assert 'crm-superadmin' in fake.admin_users['u1']['roles']


def test_does_nothing_when_a_superadmin_already_exists():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='existing@demo.local', username='existing', roles=['crm-superadmin'])
    fake.add_admin_user(id='u2', email='owner@demo.local', username='owner', roles=['crm-admin'])
    client = make_client(fake)
    bootstrap_superadmin(client, email='owner@demo.local')
    assert 'crm-superadmin' not in fake.admin_users['u2']['roles']
    assert fake.admin_users['u1']['roles'] == ['crm-superadmin']


def test_logs_and_does_not_raise_when_email_not_found(caplog):
    fake = FakeKeycloak()
    client = make_client(fake)
    with caplog.at_level(logging.WARNING):
        bootstrap_superadmin(client, email='nobody@demo.local')  # must not raise
    assert 'not found' in caplog.text.lower()


def test_logs_and_does_not_raise_when_keycloak_unavailable(caplog):
    fake = FakeKeycloak()
    fake.unavailable = True
    client = make_client(fake)
    with caplog.at_level(logging.WARNING):
        bootstrap_superadmin(client, email='owner@demo.local')  # must not raise
    assert caplog.text  # something was logged


def test_skips_cleanly_when_email_not_configured(caplog):
    fake = FakeKeycloak()
    client = make_client(fake)
    with caplog.at_level(logging.INFO):
        bootstrap_superadmin(client, email='')
    assert 'not configured' in caplog.text.lower() or 'skip' in caplog.text.lower()


def test_skips_cleanly_when_admin_client_not_configured(caplog):
    client = KeycloakAdminClient(base_url='', client_id='', client_secret='', http_client=FakeKeycloak().http_client())
    with caplog.at_level(logging.INFO):
        bootstrap_superadmin(client, email='owner@demo.local')  # must not raise despite client being unconfigured
