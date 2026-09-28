import json
import importlib
import stat
import pytest

from sqlalchemy import select

from app.models import Task, User
from fake_keycloak import FakeKeycloak
from helpers import database
from test_keycloak_admin import make_client


def seed_accounts(fake, database_url):
    fake.add_admin_user(id='irina-id', username='irina.demo@educrm-demo.ru',
                        email='irina.demo@educrm-demo.ru', first_name='Ирина', last_name='Демо',
                        roles=['crm-admin', 'crm-superadmin'])
    fake.add_admin_user(id='anna-id', username='anna.demo@educrm-demo.ru',
                        email='anna.demo@educrm-demo.ru', first_name='Анна', last_name='Демо',
                        roles=['crm-user'])
    fake.add_admin_user(id='pavel-id', username='pavel.demo@educrm-demo.ru',
                        email='pavel.demo@educrm-demo.ru', first_name='Павел', last_name='Демо',
                        roles=['crm-supervisor'])
    fake.add_admin_user(id='real-id', username='real.person', email='real@company.ru',
                        roles=['crm-user'])
    with database(database_url) as db:
        for subject, email, role in (
            ('irina-id', 'irina.demo@educrm-demo.ru', 'crm-admin'),
            ('anna-id', 'anna.demo@educrm-demo.ru', 'crm-user'),
            ('pavel-id', 'pavel.demo@educrm-demo.ru', 'crm-supervisor'),
        ):
            db.add(User(keycloak_sub=subject, email=email, full_name='Старое имя', roles=[role]))
        db.flush()
        anna_id = db.scalar(select(User.id).where(User.keycloak_sub == 'anna-id'))
        db.add(Task(title='Историческая задача', creator_id=anna_id))
        db.commit()


def test_reconcile_demo_accounts_preserves_subjects_and_task_history(database_url, tmp_path):
    reconcile_demo_accounts = importlib.import_module('app.reconcile_demo_accounts').reconcile_demo_accounts
    fake = FakeKeycloak()
    seed_accounts(fake, database_url)
    client = make_client(fake)
    output = tmp_path / 'credentials.json'
    with database(database_url) as db:
        preview = reconcile_demo_accounts(db, client, apply=False)
        assert preview['renamed'] == 3
        assert preview['created'] == 2
        assert not output.exists()
        assert fake.admin_users['irina-id']['username'] == 'irina.demo@educrm-demo.ru'

    with database(database_url) as db:
        result = reconcile_demo_accounts(db, client, apply=True, credentials_out=output,
                                         password_factory=lambda: 'TemporarySecret123456789')
        db.commit()
        assert result == preview

    users = {u.username: u for u in client.list_users() if u.email}
    assert set(users) == {'irina_super_admin', 'manager_1', 'manager_2', 'admin_1', 'admin_2', 'real.person'}
    assert users['irina_super_admin'].id == 'irina-id'
    # Irina holds only crm-superadmin directly; crm-admin and crm-supervisor come from the composite role.
    assert set(users['irina_super_admin'].roles) == {'crm-superadmin'}
    assert set(users['manager_1'].roles) == set(users['manager_2'].roles) == {'crm-user'}
    assert set(users['admin_1'].roles) == set(users['admin_2'].roles) == {'crm-admin'}
    assert client.count_users_with_role('crm-superadmin') == 1
    assert client.count_users_with_role('crm-supervisor') == 0
    assert fake.admin_users['real-id']['email'] == 'real@company.ru'
    with database(database_url) as db:
        assert db.scalar(select(Task.creator_id)) == db.scalar(select(User.id).where(User.keycloak_sub == 'anna-id'))
        assert db.scalar(select(User.email).where(User.keycloak_sub == 'irina-id')) == 'irina_super_admin@educrm-demo.ru'
        # The CRM keeps her effective roles until her next sign-in refreshes them from the token.
        assert db.scalar(select(User.roles).where(User.keycloak_sub == 'irina-id')) == ['crm-admin', 'crm-superadmin', 'crm-supervisor']
        assert db.scalar(select(User.roles).where(User.keycloak_sub == 'pavel-id')) == ['crm-user']
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert set(json.loads(output.read_text())) == {'irina_super_admin', 'manager_1', 'manager_2', 'admin_1', 'admin_2'}
    assert set(fake.logged_out_users) == {'irina-id', 'anna-id', 'pavel-id'}
    with database(database_url) as db:
        assert reconcile_demo_accounts(db, client, apply=False) == {
            'renamed': 0, 'created': 0, 'role_changes': 0,
        }


def test_reconcile_requires_realm_settings_that_preserve_custom_logins(database_url, tmp_path):
    reconcile = importlib.import_module('app.reconcile_demo_accounts').reconcile_demo_accounts
    fake = FakeKeycloak()
    seed_accounts(fake, database_url)
    fake.registration_email_as_username = True
    with database(database_url) as db:
        with pytest.raises(ValueError, match='email-as-username'):
            reconcile(db, make_client(fake), apply=True, credentials_out=tmp_path / 'passwords.json')
    assert fake.admin_users['pavel-id']['username'] == 'pavel.demo@educrm-demo.ru'
    assert not (tmp_path / 'passwords.json').exists()


def test_reconcile_repairs_keycloak_normalized_demo_logins(database_url, tmp_path):
    reconcile = importlib.import_module('app.reconcile_demo_accounts').reconcile_demo_accounts
    fake = FakeKeycloak()
    seed_accounts(fake, database_url)
    client = make_client(fake)
    with database(database_url) as db:
        reconcile(db, client, apply=True, credentials_out=tmp_path / 'first.json',
                  password_factory=lambda: 'FirstTemporarySecret123456')
        db.commit()
    for account in fake.admin_users.values():
        if account['email'].endswith('@educrm-demo.ru'):
            account['username'] = account['email']
    with database(database_url) as db:
        assert reconcile(db, client, apply=False) == {
            'renamed': 5, 'created': 0, 'role_changes': 0,
        }
        reconcile(db, client, apply=True, credentials_out=tmp_path / 'corrected.json',
                  password_factory=lambda: 'CorrectedTemporarySecret123456')
        db.commit()
    assert {u.username for u in client.list_users() if u.email.endswith('@educrm-demo.ru')} == {
        'irina_super_admin', 'admin_1', 'admin_2', 'manager_1', 'manager_2',
    }
    assert set(json.loads((tmp_path / 'corrected.json').read_text())) == {
        'irina_super_admin', 'admin_1', 'admin_2', 'manager_1', 'manager_2',
    }
