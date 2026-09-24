"""Interaction reports (docs/specification.md "Functional requirements"; D-221): filters by period,
universities, IT directions, IT products, responsible and status; selectable columns; xlsx / xls /
pdf downloads."""
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import openpyxl
import xlrd
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.models import AuditEvent, StatusChange
from helpers import database, login


def create_university(client, name, city='Москва'):
    response = client.post('/api/v1/universities', json={'name': name, 'city': city, 'contact': ''})
    assert response.status_code == 201, response.text
    return response.json()


def create_product(client, name, direction_names):
    direction_ids = []
    for direction in direction_names:
        created = client.post('/api/v1/it-directions', json={'name': direction})
        if created.status_code == 201:
            direction_ids.append(created.json()['id'])
        else:  # already exists
            direction_ids.append(next(d['id'] for d in client.get('/api/v1/it-directions').json() if d['name'] == direction))
    response = client.post('/api/v1/it-products', json={'vendor': 'РТК ИТ', 'name': name, 'direction_ids': direction_ids})
    assert response.status_code == 201, response.text
    return response.json()


def create_launch(client, university_id, *, program='Python', owner='Ирина Петрова', deadline='2026-10-01', it_product_id=None):
    body = {'university_id': university_id, 'program': program, 'product': 'Учебная среда', 'owner': owner,
            'students': 30, 'deadline': deadline}
    if it_product_id is not None:
        body['it_product_id'] = it_product_id
    response = client.post('/api/v1/launches', json=body)
    assert response.status_code == 201, response.text
    return response.json()


def backdate_history(database_url, launch_id, when):
    with database(database_url) as db:
        db.execute(update(StatusChange).where(StatusChange.launch_id == launch_id).values(created_at=when))
        db.commit()


def report(client, **params):
    response = client.get('/api/v1/reports/interactions', params=params)
    assert response.status_code == 200, response.text
    return response.json()


def seed(client, database_url):
    """Two institutions, two products in two directions, three interactions."""
    msu = create_university(client, 'Колледж связи', city='Казань')
    tech = create_university(client, 'Технический университет', city='Омск')
    postgres = create_product(client, 'PostgreSQL', ['Базы данных'])
    k8s = create_product(client, 'Kubernetes', ['DevOps'])
    a = create_launch(client, msu['id'], program='Аналитика данных', owner='Ирина Петрова', deadline='2026-09-10', it_product_id=postgres['id'])
    b = create_launch(client, tech['id'], program='Облачные технологии', owner='Олег Кузнецов', deadline='2026-12-01', it_product_id=k8s['id'])
    c = create_launch(client, tech['id'], program='Без продукта', owner='Ирина Петрова', deadline='2027-03-01')
    backdate_history(database_url, a['id'], datetime(2026, 9, 5, tzinfo=timezone.utc))
    backdate_history(database_url, b['id'], datetime(2026, 11, 20, tzinfo=timezone.utc))
    backdate_history(database_url, c['id'], datetime(2027, 2, 1, tzinfo=timezone.utc))
    return {'msu': msu, 'tech': tech, 'postgres': postgres, 'k8s': k8s, 'a': a, 'b': b, 'c': c}


def test_launch_links_to_an_active_catalog_product(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = create_university(client, 'Вуз')
    product = create_product(client, 'PostgreSQL', ['Базы данных'])
    launch = create_launch(client, university['id'], it_product_id=product['id'])
    assert launch['it_product_id'] == product['id']

    missing = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'x', 'product': 'x', 'owner': 'x', 'students': 1,
        'deadline': '2026-10-01', 'it_product_id': 999,
    })
    assert missing.status_code == 422
    assert missing.json()['details'][0]['field'] == 'it_product_id'

    unlinked = create_launch(client, university['id'])
    linked = client.put(f"/api/v1/launches/{unlinked['id']}/it-product", json={'it_product_id': product['id']})
    assert linked.status_code == 200, linked.text
    assert linked.json()['it_product_id'] == product['id']
    cleared = client.put(f"/api/v1/launches/{unlinked['id']}/it-product", json={'it_product_id': None})
    assert cleared.json()['it_product_id'] is None


def test_default_report_has_the_specification_columns(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    data = seed(client, database_url)

    body = report(client)
    assert [c['key'] for c in body['columns']] == ['university', 'program', 'it_direction', 'it_product', 'status', 'owner']
    assert body['total'] == 3
    rows = {r['program']: r for r in body['rows']}
    assert rows['Аналитика данных'] == {
        'university': 'Колледж связи', 'program': 'Аналитика данных', 'it_direction': 'Базы данных',
        'it_product': 'РТК ИТ — PostgreSQL', 'status': rows['Аналитика данных']['status'], 'owner': 'Ирина Петрова',
    }
    assert rows['Аналитика данных']['status']  # the default workflow's first status name
    # No catalog link: the interaction's own free-text product, no direction.
    assert rows['Без продукта']['it_product'] == 'Учебная среда'
    assert rows['Без продукта']['it_direction'] == ''
    assert data  # seeded


def test_report_filters(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    d = seed(client, database_url)
    programs = lambda body: sorted(r['program'] for r in body['rows'])

    assert programs(report(client, university_id=d['tech']['id'])) == ['Без продукта', 'Облачные технологии']
    assert programs(report(client, it_product_id=d['postgres']['id'])) == ['Аналитика данных']
    direction = next(x for x in client.get('/api/v1/it-directions').json() if x['name'] == 'DevOps')
    assert programs(report(client, it_direction_id=direction['id'])) == ['Облачные технологии']
    assert programs(report(client, owner='Олег Кузнецов')) == ['Облачные технологии']
    assert programs(report(client, owner=['Олег Кузнецов', 'Ирина Петрова'])) == ['Аналитика данных', 'Без продукта', 'Облачные технологии']
    status_id = d['a']['status_id']
    assert len(report(client, status_id=status_id)['rows']) == 3  # all still in the first status


def test_period_includes_an_interaction_with_a_status_change_or_launch_date_inside_it(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    programs = lambda body: sorted(r['program'] for r in body['rows'])

    # September: A changed status on 5 Sep and launches 10 Sep.
    assert programs(report(client, period_from='2026-09-01', period_to='2026-09-30')) == ['Аналитика данных']
    # Late November – December: B changed status on 20 Nov and launches 1 Dec.
    assert programs(report(client, period_from='2026-11-15', period_to='2026-12-31')) == ['Облачные технологии']
    # Only a launch date inside: C launches 1 Mar 2027, its status change was 1 Feb.
    assert programs(report(client, period_from='2027-03-01', period_to='2027-03-31')) == ['Без продукта']
    bad = client.get('/api/v1/reports/interactions', params={'period_from': '2026-10-01', 'period_to': '2026-09-01'})
    assert bad.status_code == 422


def test_selected_columns_and_validation(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    body = report(client, column=['university', 'students', 'deadline', 'comment'])
    assert [c['key'] for c in body['columns']] == ['university', 'students', 'deadline', 'comment']
    assert set(body['rows'][0]) == {'university', 'students', 'deadline', 'comment'}

    unknown = client.get('/api/v1/reports/interactions', params={'column': 'salary'})
    assert unknown.status_code == 422


def test_manager_only_reports_on_assigned_universities(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    login(client, keycloak, roles=('crm-user',), subject='kc-manager', name='Менеджер Без Вузов', email='m@demo.local')
    assert report(client)['total'] == 0


def test_exports_open_with_the_selected_columns(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    params = {'column': ['university', 'it_product', 'owner']}

    xlsx = client.get('/api/v1/reports/interactions/export', params={**params, 'format': 'xlsx'})
    assert xlsx.status_code == 200, xlsx.text
    assert 'attachment' in xlsx.headers['content-disposition'] and '.xlsx' in xlsx.headers['content-disposition']
    sheet = openpyxl.load_workbook(io.BytesIO(xlsx.content)).active
    values = list(sheet.values)
    assert values[0] == ('Учебное заведение', 'ИТ-продукт', 'Ответственный')
    assert ('Колледж связи', 'РТК ИТ — PostgreSQL', 'Ирина Петрова') in values
    assert len(values) == 4

    xls = client.get('/api/v1/reports/interactions/export', params={**params, 'format': 'xls'})
    assert xls.status_code == 200, xls.text
    book = xlrd.open_workbook(file_contents=xls.content)
    sh = book.sheet_by_index(0)
    assert sh.row_values(0) == ['Учебное заведение', 'ИТ-продукт', 'Ответственный']
    assert sh.nrows == 4

    pdf = client.get('/api/v1/reports/interactions/export', params={**params, 'format': 'pdf'})
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers['content-type'] == 'application/pdf'
    assert pdf.content.startswith(b'%PDF')
    assert b'DejaVuSans' in pdf.content  # the embedded Cyrillic font

    bad = client.get('/api/v1/reports/interactions/export', params={'format': 'docx'})
    assert bad.status_code == 422


def test_export_is_audited(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    client.get('/api/v1/reports/interactions/export', params={'format': 'xlsx', 'owner': 'Ирина Петрова'})
    with database(database_url) as db:
        events = db.query(AuditEvent).filter(AuditEvent.action == 'report.export').all()
    assert len(events) == 1
    assert events[0].payload['format'] == 'xlsx'
    assert events[0].payload['rows'] == 2
    assert events[0].payload['filters']['owner'] == ['Ирина Петрова']


def test_report_options_list_owners_and_statuses_in_scope(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    options = client.get('/api/v1/reports/options').json()
    assert options['owners'] == ['Ирина Петрова', 'Олег Кузнецов']
    assert options['statuses'] and {'id', 'name', 'workflow'} <= set(options['statuses'][0])
    assert [c['key'] for c in options['columns'] if c['default']] == ['university', 'program', 'it_direction', 'it_product', 'status', 'owner']


def test_ten_reports_build_in_parallel(app, client, keycloak, database_url):
    """Specification: "withstand building at least 10 parallel reports". Ten concurrent exports, all formats."""
    login(client, keycloak, roles=('crm-supervisor',))
    seed(client, database_url)
    cookies = dict(client.cookies)

    def build(fmt):
        with TestClient(app, cookies=cookies) as parallel:
            return parallel.get('/api/v1/reports/interactions/export', params={'format': fmt}).status_code

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(build, ['xlsx', 'xls', 'pdf', 'xlsx', 'xls', 'pdf', 'xlsx', 'xls', 'pdf', 'xlsx']))
    assert codes == [200] * 10
