import httpx
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


def test_count_users_with_role_uses_role_members_endpoint_not_capped_list_users():
    # Simulates the old bug: if count_users_with_role still listed every user via GET /users (which
    # Keycloak caps at 100 by default) and filtered client-side, a realm with more users than that
    # cap could under-count. Here the fake's GET /users is made to return a wrong/capped answer
    # ('not a list' — obviously broken) while the real GET /roles/{name}/users endpoint returns the
    # correct membership, proving the client reads from the role-members endpoint, not /users.
    fake = FakeKeycloak()
    fake.add_admin_user(id='u1', email='a@demo.local', username='a', roles=['crm-superadmin'])
    fake.add_admin_user(id='u2', email='b@demo.local', username='b', roles=['crm-user'])
    fake.malformed_users_response = 'wrong_shape'
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


def test_non_json_body_raises_keycloak_admin_error_not_json_decode_error():
    fake = FakeKeycloak()
    fake.malformed_users_response = 'not_json'
    with pytest.raises(KeycloakAdminError):
        make_client(fake).list_users()


def test_wrong_shape_body_raises_keycloak_admin_error_not_type_error():
    fake = FakeKeycloak()
    fake.malformed_users_response = 'wrong_shape'
    with pytest.raises(KeycloakAdminError):
        make_client(fake).list_users()


def test_token_response_missing_access_token_raises_keycloak_admin_error_not_key_error():
    fake = FakeKeycloak()
    fake.token_response_missing_access_token = True
    with pytest.raises(KeycloakAdminError):
        make_client(fake).list_users()


def test_401_on_a_request_clears_the_cached_token():
    fake = FakeKeycloak()
    client = make_client(fake)
    # Prime a cached token, then make Keycloak start rejecting it (simulated by making credentials
    # wrong so the *next* token fetch would 401 too — the point here is only that the cached token
    # slot is cleared, forcing a fresh fetch rather than silently reusing the now-invalid one).
    client.list_users()
    assert client._token is not None

    def force_401(request):
        return httpx.Response(401, json={'error': 'invalid_token'})

    client._http = httpx.Client(transport=httpx.MockTransport(force_401))
    with pytest.raises(KeycloakAdminError):
        client.list_users()
    assert client._token is None
