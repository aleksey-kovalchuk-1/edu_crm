import io
import zipfile
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import importer
from app.models import AuditEvent, Contract, ITProduct, University, UniversityContact
from helpers import database, login

FIXTURES = Path(__file__).parent / 'fixtures'
XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
HEADERS = ['Наименование вуза', 'Вендор', 'Программное обеспечение', 'Номер договора', 'Подписание лицензии', 'Срок действия лицензии',
           'Статус передачи', 'ФИО менеджера', 'Ответственные от вуза', 'Комментарий', 'ИТ-направления']
ROWS = [
    ['Волжский институт цифровых технологий', 'РТК ИТ', 'Учебная среда', 'Д-100', date(2026, 1, 15), None, 'Передано', 'Анна Демо', 'Иван Демо; Мария Демо', 'Первая поставка', 'DevOps; QA'],
    ['Волжский институт цифровых технологий', 'РТК ИТ', 'Тестовый стенд', 'Д-101', '01.03.2026', '01.03.2027', '', 'Неизвестный Менеджер', '', '', 'QA'],
    ['', 'РТК ИТ', 'Учебная среда', 'Д-102', '01.03.2026', None, '', '', '', '', ''],
]


def workbook(rows, headers=HEADERS):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def head(app, keycloak):
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо', email='pavel.demo@demo.local')
        yield client


@pytest.fixture
def manager(app, keycloak):
    with TestClient(app) as client:
        me = login(client, keycloak, roles=('crm-user',), subject='kc-manager', name='Анна Демо')
        client.user_id = me['user']['id']
        yield client


def upload(client, content, filename='реестр.xlsx', content_type=XLSX_TYPE):
    return client.post('/api/v1/imports', files={'file': (filename, content, content_type)})


def uploaded(client, rows=ROWS):
    response = upload(client, workbook(rows))
    assert response.status_code == 201, response.text
    return response.json()


def count(database_url, model):
    with database(database_url) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_upload_suggests_mapping_and_previews_rows(head):
    body = uploaded(head)
    assert body['status'] == 'uploaded'
    assert body['row_count'] == 3
    assert body['header_row'] == 1
    assert all(body['mapping'][field] for field in importer.FIELDS)
    assert body['preview'][0] == {'row_number': 2, 'cells': ROWS[0][:4] + ['2026-01-15', None] + ROWS[0][6:]}
    assert body['created_by']['full_name'] == 'Павел Демо'
    fields = head.get('/api/v1/imports/fields').json()
    assert [field['name'] for field in fields if field['required']] == importer.REQUIRED_FIELDS


def test_check_reports_planned_changes_without_writing(head, manager, database_url):
    body = uploaded(head)
    report = head.post(f"/api/v1/imports/{body['id']}/check", json={'mapping': body['mapping']}).json()
    assert report['summary'] == {
        'rows': 3, 'valid': 2, 'invalid': 1, 'skipped': 0, 'with_warnings': 2,
        'created': {'universities': 1, 'it_products': 2, 'it_directions': 2, 'university_contacts': 2, 'contracts': 2},
        'updated': {'contracts': 0},
    }
    error_row = report['rows'][2]
    assert (error_row['row_number'], error_row['status']) == (4, 'error')
    assert any('Наименование вуза' in message for message in error_row['errors'])
    assert any('Неизвестный Менеджер' in warning for warning in report['rows'][1]['warnings'])
    assert count(database_url, Contract) == 0
    assert count(database_url, University) == 0


def test_apply_writes_catalogs_in_one_step_and_only_once(head, manager, database_url):
    body = uploaded(head)
    report = head.post(f"/api/v1/imports/{body['id']}/apply", json={'mapping': body['mapping']})
    assert report.status_code == 200, report.text
    assert report.json()['summary']['created']['contracts'] == 2

    with database(database_url) as db:
        first = db.scalar(select(Contract).where(Contract.contract_number == 'Д-100'))
        second = db.scalar(select(Contract).where(Contract.contract_number == 'Д-101'))
        assert first.manager_user_id == manager.user_id
        assert sorted(contact.full_name for contact in first.contacts) == ['Иван Демо', 'Мария Демо']
        assert first.transfer_status == 'transferred'
        assert first.valid_until == date(2027, 1, 15)
        product = db.scalar(select(ITProduct).where(ITProduct.name == 'Учебная среда'))
        assert [direction.name for direction in product.directions] == ['DevOps', 'QA']
        assert (second.manager_user_id, second.manager_name, second.valid_until) == (None, 'Неизвестный Менеджер', date(2027, 3, 1))
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'import.apply')) == 1

    again = head.post(f"/api/v1/imports/{body['id']}/apply", json={'mapping': body['mapping']})
    assert again.status_code == 409
    history = head.get('/api/v1/imports').json()
    assert (history[0]['id'], history[0]['status'], history[0]['summary']['valid']) == (body['id'], 'applied', 2)
    assert head.get(f"/api/v1/imports/{body['id']}").json()['report']['summary']['created']['contracts'] == 2


def test_reimport_updates_existing_records_instead_of_duplicating(head, database_url):
    first = uploaded(head, ROWS[:2])
    head.post(f"/api/v1/imports/{first['id']}/apply", json={'mapping': first['mapping']})

    changed = [list(row) for row in ROWS[:2]]
    changed[0][6] = 'Идёт передача'
    second = uploaded(head, changed)
    check = head.post(f"/api/v1/imports/{second['id']}/check", json={'mapping': second['mapping']}).json()
    assert [row['action'] for row in check['rows']] == ['update', 'update']
    assert check['summary']['created'] == {'universities': 0, 'it_products': 0, 'it_directions': 0, 'university_contacts': 0, 'contracts': 0}
    head.post(f"/api/v1/imports/{second['id']}/apply", json={'mapping': second['mapping']})

    assert (count(database_url, Contract), count(database_url, University), count(database_url, ITProduct), count(database_url, UniversityContact)) == (2, 1, 2, 2)
    with database(database_url) as db:
        assert db.scalar(select(Contract.transfer_status).where(Contract.contract_number == 'Д-100')) == 'in_progress'


def test_repeated_contract_number_uses_the_last_row(head, database_url):
    rows = [ROWS[0], [*ROWS[0][:4], '10.10.2026', None, '', '', '', '', '']]
    body = uploaded(head, rows)
    report = head.post(f"/api/v1/imports/{body['id']}/apply", json={'mapping': body['mapping']}).json()
    assert [row['status'] for row in report['rows']] == ['skipped', 'warning']
    with database(database_url) as db:
        assert db.scalar(select(Contract.signed_at).where(Contract.contract_number == 'Д-100')) == date(2026, 10, 10)


def test_mapping_problems_are_reported(head):
    body = uploaded(head)
    mapping = {**body['mapping'], 'contract_number': None, 'vendor': body['mapping']['software']}
    response = head.post(f"/api/v1/imports/{body['id']}/check", json={'mapping': mapping})
    assert response.status_code == 422
    assert {detail['field'] for detail in response.json()['details']} == {'mapping'}
    assert len(response.json()['details']) == 2


def test_file_problems_use_specific_error_codes(head, monkeypatch):
    assert upload(head, b'plain text', 'notes.txt', 'text/plain').status_code == 415
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('junk.xml', 'not a workbook')
    broken = upload(head, buffer.getvalue())
    assert broken.status_code == 422
    assert broken.json()['details'][0]['field'] == 'file'
    content = workbook(ROWS)
    monkeypatch.setattr(importer, 'MAX_FILE_BYTES', len(content) - 1)
    assert upload(head, content).status_code == 413


def test_only_heads_and_administrators_can_import(manager):
    assert upload(manager, workbook(ROWS)).status_code == 403
    assert manager.get('/api/v1/imports').status_code == 403
    assert manager.get('/api/v1/imports/fields').status_code == 403


def test_legacy_xls_file_can_be_imported(head, database_url):
    response = upload(head, (FIXTURES / 'catalog_sample.xls').read_bytes(), 'catalog_sample.xls', 'application/vnd.ms-excel')
    assert response.status_code == 201, response.text
    body = response.json()
    report = head.post(f"/api/v1/imports/{body['id']}/apply", json={'mapping': body['mapping']}).json()
    assert report['summary']['valid'] == 2
    assert count(database_url, Contract) == 2
