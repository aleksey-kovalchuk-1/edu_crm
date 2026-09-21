import pytest

from app.keycloak_admin import KeycloakAdminClient, KeycloakAdminError, KeycloakAdminUnavailable
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET, FakeKeycloak


def make_client(fake):
    return KeycloakAdminClient(
        base_url=ADMIN_BASE_URL, client_id=ADMIN_CLIENT_ID, client_secret=ADMIN_CLIENT_SECRET,
        http_client=fake.http_client(),
    )


def test_is_configured_true_with_credentials():
    assert make_client(FakeKeycloak()).is_configured() is True


def test_is_configured_false_without_credentials():
    client = KeycloakAdminClient(base_url='', client_id='', client_secret='', http_client=FakeKeycloak().http_client())
    assert client.is_configured() is False


def test_find_user_by_email_found():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='anna@demo.local', username='anna', roles=['crm-user'])
    user = make_client(fake).find_user_by_email('anna@demo.local')
    assert user is not None
    assert user.id == 'u1'
    assert user.roles == ['crm-user']


def test_find_user_by_email_not_found():
    fake = FakeKeycloak()
    assert make_client(fake).find_user_by_email('nobody@demo.local') is None


def test_list_users_returns_all():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-user'])
    fake.add_admin_user(id='u2', email='b@demo.local', username='b', roles=[])
    users = make_client(fake).list_users()
    assert {u.id for u in users} == {'u1', 'u2'}


def test_assign_realm_role_adds_it():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=[])
    make_client(fake).assign_realm_role('u1', 'crm-superadmin')
    assert fake.admin_users['u1']['roles'] == ['crm-superadmin']


def test_remove_realm_role_removes_it():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-superadmin', 'crm-admin'])
    make_client(fake).remove_realm_role('u1', 'crm-superadmin')
    assert fake.admin_users['u1']['roles'] == ['crm-admin']


def test_count_users_with_role():
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-superadmin'])
    fake.add_admin_user(id='u2', email='b@demo.local', username='b', roles=['crm-user'])
    assert make_client(fake).count_users_with_role('crm-superadmin') == 1


def test_get_password_policy():
    fake = FakeKeycloak()
    fake.realm_password_policy = "length(12) and notUsername"
    assert make_client(fake).get_password_policy() == "length(12) and notUsername"


def test_wrong_admin_credentials_raise():
    fake = FakeKeycloak()
    client = KeycloakAdminClient(base_url=ADMIN_BASE_URL, client_id=ADMIN_CLIENT_ID, client_secret='wrong', http_client=fake.http_client())
    with pytest.raises(KeycloakAdminError):
        client.list_users()


def test_keycloak_unavailable_raises_unavailable():
    fake = FakeKeycloak()
    fake.unavailable = True
    with pytest.raises(KeycloakAdminUnavailable):
        make_client(fake).list_users()
