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
