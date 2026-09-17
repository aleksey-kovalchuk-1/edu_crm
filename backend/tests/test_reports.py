"""Report generation: filters, columns, async job, xlsx/xls/pdf/json export, university scope (T-050-T-054,
D-180-D-183).

The report job is run directly against a claimed `BackgroundJob` row, exactly the way `app.worker.run`
would dispatch it -- see `tests/test_jobs.py` and `tests/test_document_api.py` for the same pattern.
"""
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import xlrd
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import jobs
from app.models import AuditEvent, BackgroundJob, ReportFile
from app.report_jobs import run_report_generate
from app.reports import REPORT_COLUMNS
from helpers import database, login

OLE_SIGNATURE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


# ---------- fixtures ----------

@pytest.fixture
def head(app, keycloak):
    with TestClient(app) as client:
        login(client, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо', email='pavel.demo@demo.local')
        yield client


@pytest.fixture
def manager(app, keycloak):
    with TestClient(app) as client:
        me = login(client, keycloak, roles=('crm-user',), subject='kc-manager', name='Анна Демо', email='anna.demo@demo.local')
        client.user_id = me['user']['id']
        yield client


def create_university(client, name, **extra):
    response = client.post('/api/v1/universities', json={'name': name, 'city': 'Москва', 'contact': '', **extra})
    assert response.status_code == 201, response.text
    return response.json()


def create_direction(client, name):
    response = client.post('/api/v1/it-directions', json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()


def create_product(client, name, direction_ids=(), vendor='РТК ИТ'):
    response = client.post('/api/v1/it-products', json={'vendor': vendor, 'name': name, 'direction_ids': list(direction_ids)})
    assert response.status_code == 201, response.text
    return response.json()


def assign(client, university_id, *user_ids):
    response = client.put(f'/api/v1/universities/{university_id}/managers', json={'user_ids': list(user_ids)})
    assert response.status_code == 200, response.text
    return response.json()


def create_launch(client, university, *, program='Python', product='Учебная среда', owner='Анна Демо',
                   deadline='2026-10-01', students=30):
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': program, 'product': product, 'owner': owner,
        'students': students, 'deadline': deadline,
    })
    assert response.status_code == 201, response.text
    return response.json()


def default_workflow(client):
    return next(w for w in client.get('/api/v1/workflows').json() if w['is_default'])


def request_report(client, **body):
    response = client.post('/api/v1/reports', json=body)
    assert response.status_code == 202, response.text
    return response.json()


def run_report(app, database_url, job_id):
    """Runs the report_generate handler exactly once, the way `app.worker.run` would for a claimed job."""
    with database(database_url) as db:
        job = db.get(BackgroundJob, job_id)
        result = run_report_generate(db, job, settings=app.state.settings)
        jobs.finish(db, job, result=result)
    return result


def download(client, job_id):
    response = client.get(f'/api/v1/reports/{job_id}/download')
    assert response.status_code == 200, response.text
    return response


# ---------- tests ----------

def test_columns_endpoint_lists_expected_keys(head):
    columns = head.get('/api/v1/reports/columns').json()
    assert [c['key'] for c in columns] == [
        'university', 'it_direction', 'it_product', 'program', 'workflow', 'status', 'responsible',
        'deadline', 'last_status_change_at',
    ]
    assert all(c['label'] for c in columns)


def test_json_report_matches_a_known_fixture_row(app, head, database_url):
    university = create_university(head, 'Северный технологический университет')
    direction = create_direction(head, 'DevOps')
    create_product(head, 'Учебная среда', direction_ids=[direction['id']])
    launch = create_launch(head, university, program='Python', product='Учебная среда', owner='Иван Петров', deadline='2026-11-15')
    workflow = default_workflow(head)
    status = workflow['statuses'][0]

    job = request_report(head, format='json')
    run_report(app, database_url, job['id'])
    body = download(head, job['id'])
    assert body.headers['content-type'] == 'application/json'
    payload = json.loads(body.content)

    assert [c['key'] for c in payload['columns']] == list(REPORT_COLUMNS)
    [row] = [r for r in payload['rows'] if r['id'] == launch['id']]
    last_status_change_at = row.pop('last_status_change_at')
    assert row == {
        'id': launch['id'], 'university_id': university['id'], 'status_id': status['id'],
        'university': university['name'], 'it_direction': 'DevOps', 'it_product': 'Учебная среда',
        'program': 'Python', 'workflow': workflow['name'], 'status': status['name'],
        'responsible': 'Иван Петров', 'deadline': '2026-11-15',
    }
    assert last_status_change_at  # the launch's creation already wrote one status_changes row

    with database(database_url) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == 'report.generate')).all()
        assert len(events) == 1 and events[0].payload['format'] == 'json'
        download_events = db.scalars(select(AuditEvent).where(AuditEvent.action == 'report.download')).all()
        assert len(download_events) == 1


def test_xlsx_report_contains_exactly_the_selected_columns_and_rows(app, head, database_url):
    university = create_university(head, 'Вуз А')
    create_launch(head, university, program='Java', deadline='2026-09-01')

    job = request_report(head, format='xlsx', columns=['university', 'program', 'status'])
    run_report(app, database_url, job['id'])
    body = download(head, job['id'])
    assert body.headers['content-type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    sheet = load_workbook(io.BytesIO(body.content)).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == ('Университет', 'Программа', 'Статус')
    assert len(rows) == 2
    assert rows[1][0] == 'Вуз А' and rows[1][1] == 'Java'


def test_legacy_xls_report_has_the_ole_signature_and_correct_cells(app, head, database_url):
    university = create_university(head, 'Вуз Б')
    create_launch(head, university, program='Go', deadline='2026-09-05')

    job = request_report(head, format='xls', columns=['university', 'program'])
    run_report(app, database_url, job['id'])
    body = download(head, job['id'])
    assert body.headers['content-type'] == 'application/vnd.ms-excel'
    assert body.content.startswith(OLE_SIGNATURE)

    book = xlrd.open_workbook(file_contents=body.content)
    sheet = book.sheet_by_index(0)
    assert sheet.row_values(0) == ['Университет', 'Программа']
    assert sheet.row_values(1) == ['Вуз Б', 'Go']


def test_pdf_report_survives_cyrillic_round_trip(app, head, database_url):
    university = create_university(head, 'Восточный политехнический институт')
    create_launch(head, university, program='Управление проектами', deadline='2026-09-10')

    job = request_report(head, format='pdf', columns=['university', 'program'])
    run_report(app, database_url, job['id'])
    body = download(head, job['id'])
    assert body.headers['content-type'] == 'application/pdf'
    assert body.content.startswith(b'%PDF-')

    text = ''.join(page.extract_text() for page in PdfReader(io.BytesIO(body.content)).pages)
    assert 'Восточный политехнический институт' in text
    assert 'Управление проектами' in text
    assert 'Университет' in text  # header, also Cyrillic


def test_report_never_returns_rows_outside_the_managers_scope(app, head, manager, database_url):
    own = create_university(head, 'Вуз менеджера')
    other = create_university(head, 'Другой вуз')
    assign(head, own['id'], manager.user_id)
    create_launch(head, own, program='Свой')
    create_launch(head, other, program='Чужой')

    # Even an explicit request for both universities must not leak the one outside scope.
    job = request_report(manager, format='json', university_ids=[own['id'], other['id']])
    run_report(app, database_url, job['id'])
    payload = json.loads(download(manager, job['id']).content)
    assert [r['program'] for r in payload['rows']] == ['Свой']
    assert {r['university_id'] for r in payload['rows']} == {own['id']}


def test_filters_by_period_status_and_it_direction(app, head, database_url):
    university = create_university(head, 'Вуз В')
    direction = create_direction(head, 'Data')
    create_product(head, 'Платформа данных', direction_ids=[direction['id']])
    early = create_launch(head, university, program='Ранний', product='Платформа данных', deadline='2026-01-10')
    late = create_launch(head, university, program='Поздний', product='Другой продукт', deadline='2026-12-20')
    workflow = default_workflow(head)
    second_status = workflow['statuses'][1]

    job = request_report(head, format='json', period_from='2026-01-01', period_to='2026-06-30', it_direction_ids=[direction['id']])
    run_report(app, database_url, job['id'])
    payload = json.loads(download(head, job['id']).content)
    assert [r['id'] for r in payload['rows']] == [early['id']]
    assert payload['rows'][0]['it_direction'] == 'Data'

    job2 = request_report(head, format='json', status_ids=[second_status['id']])
    run_report(app, database_url, job2['id'])
    payload2 = json.loads(download(head, job2['id']).content)
    assert payload2['rows'] == []  # neither launch has moved to the second status yet
    assert late['id'] not in [r['id'] for r in payload2['rows']]


def test_download_requires_ownership_and_readiness(app, head, manager, database_url):
    university = create_university(head, 'Вуз Г')
    assign(head, university['id'], manager.user_id)
    job = request_report(head, format='json')

    still_running = manager.get(f"/api/v1/reports/{job['id']}/download")
    # The job belongs to `head`; a different user gets 404, not a "not ready yet" 409.
    assert still_running.status_code == 404

    not_ready = head.get(f"/api/v1/reports/{job['id']}/download")
    assert not_ready.status_code == 409

    run_report(app, database_url, job['id'])
    assert head.get(f"/api/v1/reports/{job['id']}/download").status_code == 200
    assert head.get('/api/v1/reports/999999/download').status_code == 404


def test_ten_parallel_report_jobs_complete(app, head, database_url):
    university = create_university(head, 'Вуз для нагрузки')
    create_launch(head, university, program='Нагрузочный тест')
    job_ids = [request_report(head, format='json')['id'] for _ in range(10)]

    def drain_one():
        engine = create_engine(database_url)
        try:
            session_factory = sessionmaker(bind=engine)
            with session_factory() as db:
                claimed = jobs.claim_next(db)
                if claimed is None:
                    return None
                result = run_report_generate(db, claimed, settings=app.state.settings)
                jobs.finish(db, claimed, result=result)
                return claimed.id
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=10) as pool:
        processed = [f.result() for f in [pool.submit(drain_one) for _ in range(10)]]

    assert sorted(processed) == sorted(job_ids)
    with database(database_url) as db:
        succeeded = db.scalars(select(BackgroundJob).where(BackgroundJob.id.in_(job_ids), BackgroundJob.status == 'succeeded')).all()
        assert len(succeeded) == 10
        files = db.scalars(select(ReportFile).where(ReportFile.job_id.in_(job_ids))).all()
        assert len(files) == 10
