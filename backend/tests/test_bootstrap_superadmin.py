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
    sleeps = []
    with caplog.at_level(logging.WARNING):
        # Small retry window so this test doesn't actually wait the real ~60s default.
        bootstrap_superadmin(
            client, email='owner@demo.local', sleep=sleeps.append, retry_interval=1, retry_timeout=2,
        )  # must not raise
    assert caplog.text  # something was logged
    assert sleeps  # it did retry at least once before giving up


def test_retries_then_succeeds_once_keycloak_becomes_reachable(caplog):
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='owner@demo.local', username='owner', roles=['crm-admin'])
    # The first two requests (of any kind) fail as if Keycloak weren't reachable yet; everything
    # after that behaves normally — simulating the cold-start race this retry loop exists for.
    fake.unavailable_calls_remaining = 2
    client = make_client(fake)
    sleeps = []
    with caplog.at_level(logging.INFO):
        bootstrap_superadmin(
            client, email='owner@demo.local', sleep=sleeps.append, retry_interval=1, retry_timeout=30,
        )
    assert 'crm-superadmin' in fake.admin_users['u1']['roles']
    assert sleeps  # it had to retry before succeeding


def test_gives_up_after_retry_timeout_without_raising_and_without_granting(caplog):
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='owner@demo.local', username='owner', roles=['crm-admin'])
    fake.unavailable = True  # never comes back within the retry window
    client = make_client(fake)
    sleeps = []
    with caplog.at_level(logging.WARNING):
        bootstrap_superadmin(
            client, email='owner@demo.local', sleep=sleeps.append, retry_interval=1, retry_timeout=3,
        )  # must not raise
    assert 'gave up' in caplog.text.lower()
    assert 'crm-superadmin' not in fake.admin_users['u1']['roles']
    # retry_interval=1, retry_timeout=3 -> retries at elapsed 0,1,2 then gives up at elapsed 3
    assert len(sleeps) == 3


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
