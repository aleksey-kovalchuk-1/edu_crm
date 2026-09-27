import httpx
import pytest

from app import keycloak_admin
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


def test_create_account_starts_disabled_and_can_be_enabled_after_role_assignment():
    fake = FakeKeycloak()
    client = make_client(fake)
    user_id = client.create_user(
        username='admin_1', email='admin_1@example.test', first_name='Администратор',
        last_name='Один', temporary_password='TemporarySecret123456789',
    )
    assert fake.admin_users[user_id]['enabled'] is False
    assert fake.admin_users[user_id]['temporary_password'] == 'TemporarySecret123456789'
    client.assign_realm_role(user_id, 'crm-admin')
    client.set_user_enabled(user_id, True)
    assert fake.admin_users[user_id]['enabled'] is True
    assert fake.admin_users[user_id]['roles'] == ['crm-admin']


def test_create_account_reports_duplicate_and_does_not_replace_existing_user():
    fake = FakeKeycloak()
    fake.add_admin_user(id='existing', email='admin_1@example.test', username='admin_1', roles=['crm-user'])
    with pytest.raises(keycloak_admin.KeycloakAdminConflict):
        make_client(fake).create_user(
            username='admin_1', email='new@example.test', first_name='Администратор',
            last_name='Другой', temporary_password='TemporarySecret123456789',
        )
    assert len(fake.admin_users) == 1


def test_create_account_rejects_realm_that_rewrites_login_to_email():
    fake = FakeKeycloak()
    fake.registration_email_as_username = True
    with pytest.raises(KeycloakAdminError, match='username'):
        make_client(fake).create_user(
            username='admin_1', email='admin_1@example.test', first_name='Администратор',
            last_name='Один', temporary_password='TemporarySecret123456789',
        )
    assert fake.admin_users == {}


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


def test_rename_user_preserves_identity_and_logs_out_old_sessions():
    fake = FakeKeycloak()
    fake.add_admin_user(id='irina-id', email='old@educrm-demo.ru', username='old', roles=['crm-admin'])
    client = make_client(fake)
    client.update_user(
        'irina-id', username='irina_super_admin', email='irina_super_admin@educrm-demo.ru',
        first_name='Ирина', last_name='Администратор',
    )
    client.logout_user('irina-id')
    assert fake.admin_users['irina-id']['username'] == 'irina_super_admin'
    assert fake.admin_users['irina-id']['email'] == 'irina_super_admin@educrm-demo.ru'
    assert fake.logged_out_users == ['irina-id']


def test_reset_existing_account_to_temporary_password():
    fake = FakeKeycloak()
    fake.add_admin_user(id='manager-id', email='old@educrm-demo.ru', username='old', roles=['crm-user'])
    make_client(fake).set_temporary_password('manager-id', 'FreshTemporarySecret123456')
    assert fake.admin_users['manager-id']['temporary_password'] == 'FreshTemporarySecret123456'


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


def test_update_user_names_writes_names_and_middle_name_keeping_other_attributes():
    fake = FakeKeycloak()
    fake.add_admin_user(id='kc-9', email='anna@x.test', username='anna', roles=['crm-user'],
                        first_name='Анна', last_name='Петрова')
    fake.admin_users['kc-9']['attributes'] = {'department': ['sales']}
    make_client(fake).update_user_names('kc-9', first_name='Анна', last_name='Смирнова', middle_name='Сергеевна')
    stored = fake.admin_users['kc-9']
    assert (stored['firstName'], stored['lastName']) == ('Анна', 'Смирнова')
    assert stored['username'] == 'anna' and stored['email'] == 'anna@x.test'
    assert stored['attributes'] == {'department': ['sales'], 'middleName': ['Сергеевна']}


def test_update_user_names_with_empty_middle_name_clears_it():
    fake = FakeKeycloak()
    fake.add_admin_user(id='kc-9', email='anna@x.test', username='anna', roles=['crm-user'])
    fake.admin_users['kc-9']['attributes'] = {'middleName': ['Старое']}
    make_client(fake).update_user_names('kc-9', first_name='Анна', last_name='Петрова', middle_name='')
    assert fake.admin_users['kc-9']['attributes'] == {'middleName': []}


def test_update_user_names_for_missing_user_raises():
    with pytest.raises(KeycloakAdminError):
        make_client(FakeKeycloak()).update_user_names('kc-missing', first_name='А', last_name='Б', middle_name='')


def test_delete_session_ends_it_and_tolerates_an_already_gone_session():
    fake = FakeKeycloak()
    fake.admin_sessions = {'sid-1'}
    client = make_client(fake)
    client.delete_session('sid-1')
    assert fake.admin_sessions == set()
    client.delete_session('sid-1')  # already ended: not an error


def test_list_user_events_returns_login_events_for_that_user():
    fake = FakeKeycloak()
    fake.admin_events = [
        {'time': 1790000000000, 'type': 'LOGIN', 'userId': 'u1', 'ipAddress': '10.0.0.1', 'clientId': 'edu-crm-api'},
        {'time': 1790000100000, 'type': 'LOGIN_ERROR', 'userId': 'u1', 'ipAddress': '10.0.0.2', 'error': 'invalid_user_credentials'},
        {'time': 1790000200000, 'type': 'LOGIN', 'userId': 'u2', 'ipAddress': '10.0.0.3'},
    ]
    events = make_client(fake).list_user_events('u1', max_results=50)
    assert [e['type'] for e in events] == ['LOGIN', 'LOGIN_ERROR']


def test_list_user_events_without_permission_raises_forbidden():
    fake = FakeKeycloak()
    fake.events_forbidden = True
    with pytest.raises(keycloak_admin.KeycloakAdminForbidden):
        make_client(fake).list_user_events('u1')


def test_get_realm_security_reads_policy_brute_force_and_events_flag():
    fake = FakeKeycloak()
    fake.realm_events_enabled = True
    info = make_client(fake).get_realm_security()
    assert info == {'password_policy': fake.realm_password_policy, 'brute_force_protected': True,
                    'failure_factor': 30, 'events_enabled': True}
