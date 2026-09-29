"""The synthetic samples in docs/samples let reviewers try the customer-file imports (D-247) on the demo stack.

They copy the structure of the customer's files with invented values only: the real files contain personal data and
never go into the public repository.
"""
import json
import re
from pathlib import Path

import openpyxl

from app import customer_files as cf

SAMPLES = Path(__file__).resolve().parents[2] / 'docs' / 'samples'
APPLICATIONS = SAMPLES / 'applications-sample.json'
WORKBOOK = SAMPLES / 'rtk-workbook-sample.xlsx'
CUSTOMER_SHEETS = ['Сводка', 'Вузы', 'Программы', 'Продукты РТК', 'Направления', 'Ответственные', 'Договоры',
                   'Продукты договора', 'Допсоглашения', 'Источники', 'Справочники', 'Инструкция']


def test_the_applications_sample_has_the_customer_structure_and_only_invented_contacts():
    content = APPLICATIONS.read_bytes()
    assert cf.detect_kind(APPLICATIONS.name, content) == 'applications'
    entries = json.loads(content)
    assert entries[0] is None  # like the customer's file, so the skip is visible
    objects = [entry for entry in entries if entry]
    assert {tuple(entry) for entry in objects} == {
        ('Номер заявки', 'Курс', 'Фамилия', 'Имя', 'Отчество', 'Телефон', 'Email', 'Номер потока')}
    assert all(entry['Email'].endswith('@example.test') for entry in objects)
    assert all(re.fullmatch(r'7 \(900\) 000-00-\d\d', entry['Телефон']) for entry in objects)
    rows = cf.read_applications(content)
    assert all(len(cells) == 3 for _, cells in rows if isinstance(cells, list))


def test_the_workbook_sample_has_every_customer_sheet_and_fictional_universities():
    content = WORKBOOK.read_bytes()
    assert cf.detect_kind(WORKBOOK.name, content) == 'workbook'
    assert openpyxl.load_workbook(WORKBOOK, read_only=True).sheetnames == CUSTOMER_SHEETS
    sheets, rows = cf.read_workbook(content)
    assert {s['name'] for s in sheets if s['status'] == 'supported'} == {'Вузы', 'Направления', 'Продукты РТК'}
    universities = {row['values']['full_name'] for row in rows if row['sheet'] == 'Вузы'}
    # Two of the demo seed's fictional universities (matched) and one that is not in the catalogue (skipped).
    assert universities == {'Северный технологический университет', 'Волжский институт цифровых технологий',
                            'Приморский университет программной инженерии'}
    assert all(row['values']['key'] for row in rows)


def test_on_the_demo_data_the_samples_give_the_results_the_review_guide_describes(app, keycloak, database_url):
    from fastapi.testclient import TestClient

    from app.seed import seed
    from helpers import database, login

    with database(database_url) as db:
        seed(db)
        db.commit()
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо', email='pavel.demo@demo.local')
        book = client.post('/api/v1/imports', files={'file': (WORKBOOK.name, WORKBOOK.read_bytes())}).json()
        report = client.post(f"/api/v1/imports/{book['id']}/check", json={}).json()
        assert [u['name'] for u in report['unmatched_universities']] == ['Приморский университет программной инженерии']
        assert report['summary']['updated']['universities'] == 2
        assert report['summary']['created'] == {'universities': 0, 'it_directions': 2, 'it_products': 2}
        applications = client.post('/api/v1/imports', files={'file': (APPLICATIONS.name, APPLICATIONS.read_bytes())}).json()
        report = client.post(f"/api/v1/imports/{applications['id']}/check", json={}).json()
        assert report['summary']['created'] == {'course_applications': 3}
        assert report['summary']['skipped'] == 1
