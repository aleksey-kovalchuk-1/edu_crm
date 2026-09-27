import json
import importlib
import stat

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
    assert set(users['irina_super_admin'].roles) == {'crm-superadmin', 'crm-supervisor', 'crm-admin'}
    assert set(users['manager_1'].roles) == set(users['manager_2'].roles) == {'crm-user'}
    assert set(users['admin_1'].roles) == set(users['admin_2'].roles) == {'crm-admin'}
    assert client.count_users_with_role('crm-superadmin') == 1
    assert client.count_users_with_role('crm-supervisor') == 1
    assert fake.admin_users['real-id']['email'] == 'real@company.ru'
    with database(database_url) as db:
        assert db.scalar(select(Task.creator_id)) == db.scalar(select(User.id).where(User.keycloak_sub == 'anna-id'))
        assert db.scalar(select(User.email).where(User.keycloak_sub == 'irina-id')) == 'irina_super_admin@educrm-demo.ru'
        assert db.scalar(select(User.roles).where(User.keycloak_sub == 'pavel-id')) == ['crm-user']
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert set(json.loads(output.read_text())) == {'irina_super_admin', 'manager_1', 'manager_2', 'admin_1', 'admin_2'}
    assert set(fake.logged_out_users) == {'irina-id', 'anna-id', 'pavel-id'}
    with database(database_url) as db:
        assert reconcile_demo_accounts(db, client, apply=False) == {
            'renamed': 0, 'created': 0, 'role_changes': 0,
        }
