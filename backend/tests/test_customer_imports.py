import io
import json

import openpyxl
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import models
from app.security import TokenCipher
from helpers import database, login


@pytest.fixture
def head(app, keycloak):
    app.state.learner_cipher = TokenCipher(Fernet.generate_key())
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-import-head')
        yield client


def upload(client, kind, phase, content, filename):
    return client.post(f'/api/v1/customer-imports/{kind}/{phase}', files={'file': (filename, content)})


def workbook(headers, rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def applications():
    return [
        {'Номер заявки': f'A-{number}', 'Курс': 'Python', 'Фамилия': 'Тестов',
         'Имя': 'Иван', 'Отчество': 'Иванович', 'Телефон': '+7 (900) 000-00-01',
         'Email': 'learner@example.test', 'Номер потока': f'P-{number}'}
        for number in range(1, 6)
    ] + [None]


def test_application_json_previews_five_rows_and_skips_null_idempotently(head, database_url):
    content = json.dumps(applications(), ensure_ascii=False).encode()
    preview = upload(head, 'applications', 'preview', content, 'Данные оплат.json')
    assert preview.status_code == 200, preview.text
    assert preview.json()['summary']['valid'] == 5
    assert preview.json()['summary']['skipped'] == 1
    assert any('null' in warning.lower() for row in preview.json()['rows'] for warning in row['warnings'])
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.CourseApplication)) == 0
    applied = upload(head, 'applications', 'apply', content, 'Данные оплат.json')
    assert applied.status_code == 200, applied.text
    assert applied.json()['summary']['created'] == 5
    again = upload(head, 'applications', 'apply', content, 'Данные оплат.json')
    assert again.status_code == 200
    assert again.json()['summary']['created'] == 0
    with database(database_url) as db:
        apps = db.scalars(select(models.CourseApplication)).all()
        assert len(apps) == 5
        assert len({item.learner_id for item in apps}) == 1
        assert {item.payment_status for item in apps} == {'unconfirmed_by_data'}


def test_ambiguous_phone_match_is_reported_without_merging(head, database_url):
    first = head.post('/api/v1/learners', json={'last_name': 'Один', 'first_name': 'Тест', 'phone': '79000000001'}).json()
    second = head.post('/api/v1/learners', json={'last_name': 'Два', 'first_name': 'Тест', 'phone': '+7 900 000 00 01'}).json()
    content = json.dumps([applications()[0]], ensure_ascii=False).encode()
    preview = upload(head, 'applications', 'preview', content, 'заявки.json')
    assert preview.status_code == 200
    assert preview.json()['summary']['invalid'] == 1
    assert 'неоднознач' in preview.json()['rows'][0]['errors'][0].lower()
    assert set(preview.json()['rows'][0]['candidate_ids']) == {first['id'], second['id']}
    applied = upload(head, 'applications', 'apply', content, 'заявки.json')
    assert applied.json()['summary']['created'] == 0
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(models.CourseApplication)) == 0
    resolved = head.post('/api/v1/customer-imports/applications/apply',
                         files={'file': ('заявки.json', content)},
                         data={'resolved_learner_ids': json.dumps({'1': first['id']})})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['summary']['created'] == 1
    assert head.get('/api/v1/course-applications').json()[0]['learner_id'] == first['id']


def test_duplicate_external_number_is_reported_and_second_row_is_skipped(head):
    repeated = [applications()[0], {**applications()[0], 'Курс': 'Другой курс'}]
    content = json.dumps(repeated, ensure_ascii=False).encode()
    preview = upload(head, 'applications', 'preview', content, 'заявки.json').json()
    assert preview['summary']['invalid'] == 1
    assert 'повторяется' in preview['rows'][1]['errors'][0]
    assert upload(head, 'applications', 'apply', content, 'заявки.json').json()['summary']['created'] == 1
    assert head.get('/api/v1/course-applications').json()[0]['course'] == 'Python'


def test_vendor_table_splits_products_and_reuses_company_contact(head):
    content = workbook(
        ['Компания', 'Продукт', 'ФИО', 'Телефон', 'Почта', 'Способ связи'],
        [['ООО «ТДата»', 'RT.DataLake, RT.Warehouse', 'Тестовый Контакт', '00123',
          'contact@example.test', 'Почта; Чат в ТГ']],
    )
    preview = upload(head, 'vendors', 'preview', content, 'поставщики.xlsx')
    assert preview.status_code == 200, preview.text
    assert preview.json()['summary']['valid'] == 1
    applied = upload(head, 'vendors', 'apply', content, 'поставщики.xlsx')
    assert applied.status_code == 200, applied.text
    companies = head.get('/api/v1/vendor-companies').json()
    assert [company['name'] for company in companies] == ['ООО «ТДата»']
    contacts = head.get('/api/v1/vendor-contacts').json()
    assert len(contacts) == 1
    assert len(contacts[0]['product_ids']) == 2
    assert contacts[0]['preferred_channels'] == ['Почта', 'Чат в ТГ']
    assert upload(head, 'vendors', 'apply', content, 'поставщики.xlsx').json()['summary']['created'] == 0


def test_learner_reimport_does_not_erase_filled_fields_with_blank_cells(head):
    headers = ['Фамилия', 'Имя', 'Телефон', 'Email', 'Образование', 'Серия паспорта']
    initial = workbook(headers, [['Тестов', 'Иван', '00123', 'learner@example.test', 'Высшее', '0011']])
    assert upload(head, 'learners', 'apply', initial, 'слушатели.xlsx').status_code == 200
    later = workbook(headers, [['Тестов', 'Иван', '00123', 'learner@example.test', '', '']])
    assert upload(head, 'learners', 'apply', later, 'слушатели.xlsx').status_code == 200
    learner_id = head.get('/api/v1/learners').json()[0]['id']
    detail = head.get(f'/api/v1/learners/{learner_id}').json()
    assert detail['education'] == 'Высшее'
    assert detail['passport_series'] == '0011'
