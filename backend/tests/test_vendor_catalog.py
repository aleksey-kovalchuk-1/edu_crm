from alembic import command
from sqlalchemy import create_engine, select, text
from fastapi.testclient import TestClient
import pytest

from app import models
from app.db_migrate import alembic_config
from helpers import database, login


@pytest.fixture
def head(app, keycloak):
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-vendor-head')
        yield client


@pytest.fixture
def manager(app, keycloak):
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-user',), subject='kc-vendor-manager')
        yield client


def test_company_can_share_one_contact_across_two_products(database_url):
    with database(database_url) as db:
        company = models.VendorCompany(name='ООО «ТДата»')
        lake = models.ITProduct(vendor=company.name, name='RT.DataLake', company=company)
        warehouse = models.ITProduct(vendor=company.name, name='RT.Warehouse', company=company)
        contact = models.VendorContact(
            company=company,
            full_name='Тестовый Контакт',
            phone='00123456789',
            preferred_channels=['Почта', 'Чат в ТГ'],
            products=[lake, warehouse],
        )
        db.add(contact)
        db.commit()

    with database(database_url) as db:
        companies = db.scalars(select(models.VendorCompany)).all()
        assert len(companies) == 1
        assert {item.name for item in companies[0].products} == {'RT.DataLake', 'RT.Warehouse'}
        stored = db.scalar(select(models.VendorContact))
        assert {item.name for item in stored.products} == {'RT.DataLake', 'RT.Warehouse'}
        assert stored.phone == '00123456789'
        assert stored.preferred_channels == ['Почта', 'Чат в ТГ']


def test_migration_backfills_existing_products_without_changing_contracts(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0017')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            university_id = connection.execute(text("""
                INSERT INTO universities (name, city, contact)
                VALUES ('Тестовый вуз', 'Москва', '') RETURNING id
            """)).scalar_one()
            product_id = connection.execute(text("""
                INSERT INTO it_products (vendor, name)
                VALUES ('Старый поставщик', 'Текущий продукт') RETURNING id
            """)).scalar_one()
            contract_id = connection.execute(text("""
                INSERT INTO contracts (contract_number, university_id, it_product_id, signed_at,
                                       valid_until, created_at, updated_at)
                VALUES ('Д-ТЕСТ', :university_id, :product_id, '2026-01-01',
                        '2027-01-01', now(), now()) RETURNING id
            """), {'university_id': university_id, 'product_id': product_id}).scalar_one()
        command.upgrade(config, 'head')
        with engine.connect() as connection:
            row = connection.execute(text("""
                SELECT p.vendor, c.name, co.it_product_id
                FROM it_products p JOIN vendor_companies c ON c.id = p.company_id
                JOIN contracts co ON co.it_product_id = p.id
                WHERE p.id = :product_id AND co.id = :contract_id
            """), {'product_id': product_id, 'contract_id': contract_id}).one()
            assert row == ('Старый поставщик', 'Старый поставщик', product_id)
    finally:
        engine.dispose()


def test_vendor_catalog_links_contact_to_multiple_products_and_filters(head, manager):
    company_response = head.post('/api/v1/vendor-companies', json={'name': 'ООО «ТДата»'})
    assert company_response.status_code == 201, company_response.text
    company = company_response.json()
    lake = head.post('/api/v1/it-products', json={'vendor': company['name'], 'name': 'RT.DataLake'}).json()
    warehouse = head.post('/api/v1/it-products', json={'vendor': company['name'], 'name': 'RT.Warehouse'}).json()
    created = head.post('/api/v1/vendor-contacts', json={
        'company_id': company['id'], 'full_name': 'Тестовый Контакт', 'phone': '00123456789',
        'preferred_channels': ['Почта', 'Чат в ТГ'], 'product_ids': [lake['id'], warehouse['id']],
    })
    assert created.status_code == 201, created.text
    contact = created.json()
    assert contact['preferred_channels'] == ['Почта', 'Чат в ТГ']
    assert set(contact['product_ids']) == {lake['id'], warehouse['id']}
    assert manager.post('/api/v1/vendor-contacts', json={'company_id': company['id'], 'full_name': 'Новый'}).status_code == 403
    filtered = manager.get('/api/v1/vendor-contacts', params={'product_id': lake['id']}).json()
    assert [item['id'] for item in filtered] == [contact['id']]
    products = manager.get('/api/v1/it-products').json()
    assert all(item['company_id'] == company['id'] for item in products)
    assert all(item['vendor_contacts'][0]['id'] == contact['id'] for item in products)
    deactivated = head.patch(f"/api/v1/vendor-contacts/{contact['id']}", json={'is_active': False})
    assert deactivated.status_code == 200
    assert manager.get('/api/v1/vendor-contacts').json() == []


def test_contact_rejects_product_from_another_company(head):
    first = head.post('/api/v1/vendor-companies', json={'name': 'Первый'}).json()
    head.post('/api/v1/vendor-companies', json={'name': 'Второй'})
    foreign = head.post('/api/v1/it-products', json={'vendor': 'Второй', 'name': 'Продукт'}).json()
    response = head.post('/api/v1/vendor-contacts', json={
        'company_id': first['id'], 'full_name': 'Тестовый Контакт', 'product_ids': [foreign['id']],
    })
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'product_ids'
