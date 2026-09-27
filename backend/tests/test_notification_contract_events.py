from app.models import ITProduct
from helpers import database
from notification_helpers import disable, enable, ensure_user, notifications, sign_in
from test_import_api import uploaded

CONTRACT_EVENTS = ('contract_signed', 'contract_transfer_changed')


def _product(database_url):
    with database(database_url) as db:
        product = ITProduct(vendor='РТК ИТ', name='Учебная среда')
        db.add(product)
        db.commit()
        return product.id


def _setup(client, keycloak, database_url):
    anna = ensure_user(database_url, 'kc-anna', 'Анна Петрова')
    ivan = ensure_user(database_url, 'kc-ivan', 'Иван Иванов')
    for user_id in (anna, ivan):
        enable(database_url, user_id, *CONTRACT_EVENTS)
        disable(database_url, user_id, 'university_assigned')
    sign_in(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель Отдела')
    university = client.post('/api/v1/universities', json={'name': 'Вуз договоров', 'city': 'Москва', 'contact': ''}).json()
    client.put(f"/api/v1/universities/{university['id']}/managers", json={'user_ids': [anna]})
    return anna, ivan, university


def _contract_notifications(database_url):
    return sorted(n for n in notifications(database_url) if n[1] in CONTRACT_EVENTS)


def test_manual_contract_notifies_university_managers_and_the_contract_manager(client, keycloak, database_url):
    anna, ivan, university = _setup(client, keycloak, database_url)
    olga = ensure_user(database_url, 'kc-olga', 'Ольга Кузнецова', roles=('crm-admin',))  # sees every university
    enable(database_url, olga, 'contract_signed')
    product = _product(database_url)
    response = client.post('/api/v1/contracts', json={
        'contract_number': 'Д-1', 'university_id': university['id'], 'it_product_id': product,
        'signed_at': '2026-09-01', 'valid_until': '2027-09-01', 'manager_user_id': olga})
    assert response.status_code == 201, response.text
    assert _contract_notifications(database_url) == sorted(
        [(anna, 'contract_signed', 'contract', response.json()['id']), (olga, 'contract_signed', 'contract', response.json()['id'])])


def test_a_contract_manager_who_cannot_see_the_university_is_not_notified(client, keycloak, database_url):
    anna, ivan, university = _setup(client, keycloak, database_url)
    response = client.post('/api/v1/contracts', json={
        'contract_number': 'Д-3', 'university_id': university['id'], 'it_product_id': _product(database_url),
        'signed_at': '2026-09-01', 'manager_user_id': ivan})
    assert response.status_code == 201, response.text
    assert [n for n in _contract_notifications(database_url) if n[0] == ivan] == []


def test_transfer_status_change_notifies(client, keycloak, database_url):
    anna, _, university = _setup(client, keycloak, database_url)
    contract = client.post('/api/v1/contracts', json={
        'contract_number': 'Д-2', 'university_id': university['id'], 'it_product_id': _product(database_url),
        'signed_at': '2026-09-01'}).json()
    assert client.patch(f"/api/v1/contracts/{contract['id']}", json={'transfer_status': 'in_progress'}).status_code == 200
    assert (anna, 'contract_transfer_changed', 'contract', contract['id']) in _contract_notifications(database_url)


def test_imported_contracts_do_not_announce_signing(client, keycloak, database_url):
    manager = ensure_user(database_url, 'kc-manager', 'Анна Демо')  # matches the ФИО менеджера column of the fixture
    enable(database_url, manager, 'contract_signed')
    sign_in(client, keycloak, 'crm-supervisor', 'kc-head', 'Павел Демо')
    body = uploaded(client)
    applied = client.post(f"/api/v1/imports/{body['id']}/apply", json={'mapping': body['mapping']})
    assert applied.status_code == 200, applied.text
    assert [n for n in notifications(database_url) if n[1] == 'contract_signed'] == []
