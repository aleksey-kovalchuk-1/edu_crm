from datetime import date

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db_migrate import alembic_config
from app.organization import format_phone, organization_name, validate_ogrn
from helpers import database

OWNER_VALUES = {
    'name': 'ИТ Школа Ростелеком',
    'legal_name': 'Общество с ограниченной ответственностью «Ростелеком Информационные Технологии»',
    'ogrn': '1095030001131',
    'registration_date': date(2009, 4, 10),
    'legal_address': '108811, г. Москва, Киевское шоссе, 22-й км, домовладение 6, стр. 1, офис Е434',
    'postal_address': '108811, г. Москва, Киевское шоссе, 22-й км, домовладение 6, стр. 1, офис Е434',
    'contact_address': 'Москва, проспект Вернадского, д. 41',
    'phone': '+74951966205',
    'email': 'edupro@rt.ru',
}


def test_migration_seeds_the_owner_values_in_a_single_row(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0026')
    engine = create_engine(empty_database_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(
                'select id, name, legal_name, ogrn, registration_date, legal_address, postal_address, '
                'contact_address, phone, email from organization_profile')).mappings().all()
            assert len(rows) == 1 and rows[0]['id'] == 1
            assert {k: rows[0][k] for k in OWNER_VALUES} == OWNER_VALUES
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(text(
                    "insert into organization_profile (id, name, legal_name, ogrn, registration_date, legal_address, "
                    "postal_address, contact_address, phone, email) values (2, 'x', 'x', '1095030001131', "
                    "'2009-04-10', 'x', 'x', 'x', '+74951966205', 'a@b.ru')"))
    finally:
        engine.dispose()
    command.downgrade(config, '0025')
    command.upgrade(config, '0026')


@pytest.mark.parametrize('value,ok', [('1095030001131', True), ('1095030001132', False), ('12345', False), ('109503000113a', False)])
def test_validate_ogrn_checks_length_and_control_digit(value, ok):
    assert validate_ogrn(value) is ok


def test_format_phone_for_display():
    assert format_phone('+74951966205') == '+7 (495) 196-62-05'
    assert format_phone('') == ''


def test_organization_name_reads_the_row(database_url):
    with database(database_url) as db:
        assert organization_name(db) == 'ИТ Школа Ростелеком'


# --- API ---------------------------------------------------------------------------------------

from sqlalchemy import select  # noqa: E402

from app.models import AuditEvent  # noqa: E402
from helpers import login  # noqa: E402

ORG = '/api/v1/organization'
VALID = {
    'name': 'ИТ Школа Ростелеком', 'legal_name': OWNER_VALUES['legal_name'], 'ogrn': '1095030001131',
    'registration_date': '2009-04-10', 'legal_address': OWNER_VALUES['legal_address'],
    'postal_address': OWNER_VALUES['postal_address'], 'contact_address': OWNER_VALUES['contact_address'],
    'phone': '+7 (495) 196-62-05', 'email': 'edupro@rt.ru',
}


def test_any_role_reads_the_card(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    body = client.get(ORG).json()
    assert body['name'] == 'ИТ Школа Ростелеком' and body['ogrn'] == '1095030001131'
    assert body['phone'] == '+74951966205' and body['phone_display'] == '+7 (495) 196-62-05'
    assert body['registration_date'] == '2009-04-10'


@pytest.mark.parametrize('role', ['crm-user', 'crm-supervisor'])
def test_only_admins_edit(client, keycloak, role):
    login(client, keycloak, roles=(role,))
    assert client.put(ORG, json=VALID).status_code == 403


@pytest.mark.parametrize('role', ['crm-admin', 'crm-superadmin'])
def test_admin_saves_and_the_change_is_audited_by_field_names(client, keycloak, database_url, role):
    login(client, keycloak, roles=(role,))
    response = client.put(ORG, json={**VALID, 'name': 'ИТ Школа', 'phone': '8 495 196-62-05'})
    assert response.status_code == 200, response.text
    assert response.json()['name'] == 'ИТ Школа' and response.json()['phone'] == '+74951966205'
    with database(database_url) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'organization.update'))
        assert event.payload == {'fields': ['name']}


@pytest.mark.parametrize('patch,field', [
    ({'name': '  '}, 'name'),
    ({'ogrn': '1095030001132'}, 'ogrn'),
    ({'ogrn': '12345'}, 'ogrn'),
    ({'registration_date': '2999-01-01'}, 'registration_date'),
    ({'phone': '12'}, 'phone'),
    ({'email': 'bad'}, 'email'),
    ({'legal_address': 'x' * 501}, 'legal_address'),
    ({'contact_address': ''}, 'contact_address'),
])
def test_invalid_values_are_rejected_per_field(client, keycloak, patch, field):
    login(client, keycloak, roles=('crm-admin',))
    response = client.put(ORG, json={**VALID, **patch})
    assert response.status_code == 422, response.text
    assert any(d['field'] == field for d in response.json()['details'])


def test_brand_is_public_and_exposes_only_the_name(client):
    response = client.get(f'{ORG}/brand')
    assert response.status_code == 200
    assert response.json() == {'name': 'ИТ Школа Ростелеком'}
