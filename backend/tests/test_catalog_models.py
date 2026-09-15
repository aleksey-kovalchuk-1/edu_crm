from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Contract,
    ITDirection,
    ITProduct,
    University,
    UniversityContact,
    UniversityManager,
    User,
    contract_contacts,
)
from helpers import database


def add_university(db, name='Северный технологический университет'):
    university = University(name=name, city='Санкт-Петербург', contact='')
    db.add(university)
    db.flush()
    return university


def add_product(db, vendor='РТК ИТ', name='Учебная среда'):
    product = ITProduct(vendor=vendor, name=name)
    db.add(product)
    db.flush()
    return product


def add_user(db, subject='kc-manager'):
    user = User(keycloak_sub=subject, email=f'{subject}@demo.local', full_name='Анна Демо', roles=['crm-user'], is_active=True)
    db.add(user)
    db.flush()
    return user


def add_contract(db, number='Д-2026-001', **overrides):
    university = overrides.pop('university', None) or add_university(db)
    product = overrides.pop('product', None) or add_product(db)
    values = dict(contract_number=number, university_id=university.id, it_product_id=product.id,
                  signed_at=date(2026, 1, 15), valid_until=date(2027, 1, 15))
    values.update(overrides)
    contract = Contract(**values)
    db.add(contract)
    db.flush()
    return contract


def test_catalog_defaults_and_relationships(database_url):
    with database(database_url) as db:
        devops = ITDirection(name='DevOps')
        qa = ITDirection(name='QA')
        university = add_university(db)
        product = ITProduct(vendor='РТК ИТ', name='Учебная среда', directions=[qa, devops])
        db.add(product)
        contact = UniversityContact(university_id=university.id, full_name='Иван Демо', position='Проректор')
        db.add(contact)
        db.flush()
        contract = add_contract(db, university=university, product=product, contacts=[contact])
        db.commit()
        contract_id, product_id, university_id = contract.id, product.id, university.id

    with database(database_url) as db:
        stored_university = db.get(University, university_id)
        assert stored_university.is_active is True
        assert stored_university.short_name == ''
        stored_contract = db.get(Contract, contract_id)
        assert stored_contract.transfer_status == 'not_started'
        assert stored_contract.manager_user_id is None
        assert [contact.full_name for contact in stored_contract.contacts] == ['Иван Демо']
        assert [direction.name for direction in db.get(ITProduct, product_id).directions] == ['DevOps', 'QA']


def test_deleting_a_contract_removes_its_contact_links_but_not_contacts(database_url):
    with database(database_url) as db:
        university = add_university(db)
        contact = UniversityContact(university_id=university.id, full_name='Иван Демо')
        db.add(contact)
        db.flush()
        contract = add_contract(db, university=university, contacts=[contact])
        db.commit()
        db.execute(delete(Contract).where(Contract.id == contract.id))
        db.commit()
        assert db.scalar(select(func.count()).select_from(contract_contacts)) == 0
        assert db.scalar(select(func.count()).select_from(UniversityContact)) == 1


def _build_duplicate_university(db):
    add_university(db, 'Вуз')
    add_university(db, 'Вуз')


def _build_duplicate_product(db):
    add_product(db, 'Вендор', 'Продукт')
    add_product(db, 'Вендор', 'Продукт')


def _build_duplicate_direction(db):
    db.add_all([ITDirection(name='DevOps'), ITDirection(name='DevOps')])
    db.flush()


def _build_duplicate_contract_number(db):
    university = add_university(db)
    product = add_product(db)
    add_contract(db, 'Д-1', university=university, product=product)
    add_contract(db, 'Д-1', university=university, product=product)


def _build_validity_before_signing(db):
    add_contract(db, signed_at=date(2026, 5, 1), valid_until=date(2026, 4, 30))


def _build_unknown_transfer_status(db):
    add_contract(db, transfer_status='lost')


def _build_duplicate_contact(db):
    university = add_university(db)
    db.add_all([
        UniversityContact(university_id=university.id, full_name='Иван Демо'),
        UniversityContact(university_id=university.id, full_name='Иван Демо'),
    ])
    db.flush()


def _build_duplicate_manager_assignment(db):
    university = add_university(db)
    user = add_user(db)
    db.add(UniversityManager(university_id=university.id, user_id=user.id))
    db.flush()
    db.add(UniversityManager(university_id=university.id, user_id=user.id))
    db.flush()


@pytest.mark.parametrize('build', [
    _build_duplicate_university,
    _build_duplicate_product,
    _build_duplicate_direction,
    _build_duplicate_contract_number,
    _build_validity_before_signing,
    _build_unknown_transfer_status,
    _build_duplicate_contact,
    _build_duplicate_manager_assignment,
])
def test_database_rejects_invalid_catalog_data(database_url, build):
    with database(database_url) as db:
        with pytest.raises(IntegrityError):
            build(db)
            db.commit()
