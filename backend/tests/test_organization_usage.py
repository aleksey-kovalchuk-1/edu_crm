"""The organization name wherever the CRM shows it outside Настройки (spec 2026-09-27-organization-settings)."""
import io

import httpx

import openpyxl
import xlrd
from reportlab.platypus import Paragraph

from app import chart_routes
from app.chart_routes import Text
from app.email import _http_sender
from app.report_routes import pdf_story
from helpers import login, make_settings
from test_reports import create_launch, create_university

ORG = 'ИТ Школа Ростелеком'
EXPORT = '/api/v1/reports/interactions/export'


def _rename_org(client, name):
    body = client.get('/api/v1/organization').json()
    payload = {k: body[k] for k in ('name', 'legal_name', 'ogrn', 'registration_date', 'legal_address',
                                    'postal_address', 'contact_address', 'phone', 'email')}
    assert client.put('/api/v1/organization', json={**payload, 'name': name}).status_code == 200


def test_spreadsheet_exports_start_with_the_organization_name(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    university = create_university(client, 'Колледж связи')
    create_launch(client, university['id'])
    params = {'column': ['university', 'owner']}

    sheet = openpyxl.load_workbook(io.BytesIO(client.get(EXPORT, params={**params, 'format': 'xlsx'}).content)).active
    rows = list(sheet.values)
    assert rows[0][0] == ORG and rows[1] == ('Учебное заведение', 'Ответственный')

    sh = xlrd.open_workbook(file_contents=client.get(EXPORT, params={**params, 'format': 'xls'}).content).sheet_by_index(0)
    assert sh.row_values(0)[0] == ORG and sh.row_values(1) == ['Учебное заведение', 'Ответственный']


def test_renamed_organization_appears_in_the_next_export(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    _rename_org(client, 'Новое название')
    sheet = openpyxl.load_workbook(io.BytesIO(client.get(EXPORT, params={'format': 'xlsx'}).content)).active
    assert next(sheet.values)[0] == 'Новое название'


def test_pdf_report_story_starts_with_the_escaped_organization_name():
    story = pdf_story([{'key': 'u', 'label': 'Вуз'}], [{'u': 'Колледж'}], 'Период: весь', 'ООО «A & B»')
    texts = [p.text for p in story if isinstance(p, Paragraph)]
    assert texts[0] == 'ООО «A &amp; B»'


def test_charts_carry_the_organization_line(client, keycloak, monkeypatch):
    drawn = []
    monkeypatch.setattr(chart_routes, 'render_png', lambda fig: drawn.append(fig) or b'png')
    login(client, keycloak, roles=('crm-admin',))
    assert client.get('/api/v1/charts/annual', params={'format': 'png'}).status_code == 200
    assert any(isinstance(op, Text) and op.text == ORG for op in drawn[0].ops)


def test_confirmation_email_uses_the_organization_name(client, keycloak, app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body, **kwargs: sent.append((body, kwargs))
    login(client, keycloak, roles=('crm-user',), subject='kc-anna', name='Анна Петрова')
    created = client.post('/api/v1/email-senders/requests', json={'email_address': 'anna@uni-demo.ru', 'display_name': 'Анна'}).json()
    client.cookies.clear()
    client.headers.pop('X-CSRF-Token', None)
    login(client, keycloak, roles=('crm-admin',), subject='kc-adm', name='Админ Системы')
    client.post(f"/api/v1/email-senders/{created['id']}/approve")
    body, kwargs = sent[-1]
    assert kwargs['from_name'] == ORG and body.rstrip().endswith(ORG)


def test_test_email_uses_the_organization_name_without_a_chosen_sender(client, keycloak, app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body, **kwargs: sent.append((body, kwargs))
    login(client, keycloak)
    assert client.post('/api/v1/email-senders/test').status_code == 200
    body, kwargs = sent[-1]
    assert kwargs['from_name'] == ORG and body.rstrip().endswith(ORG)


def test_http_provider_receives_from_name(monkeypatch, database_url):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return httpx.Response(200, request=httpx.Request('POST', url))

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(database_url, email_provider_url='https://mail.example/send', email_provider_api_key='k')
    _http_sender(settings, 'a@b.ru', 'Тема', 'Текст', from_address='noreply@unicrm.tech', from_name=ORG)
    assert calls[0]['from_name'] == ORG
