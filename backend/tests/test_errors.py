from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.errors import CATALOGUE, AppError, ErrorCode
from app.main import create_app
from helpers import login, make_settings

ERRORS_DOC = Path(__file__).resolve().parents[2] / 'docs' / 'api' / 'errors.md'


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {'code', 'message', 'details'}
    assert body['code'] == code
    assert body['message']
    return body


def test_every_code_has_status_and_message():
    assert set(CATALOGUE) == set(ErrorCode)
    for status, message in CATALOGUE.values():
        assert 400 <= status < 600
        assert message


def test_every_code_is_documented():
    text = ERRORS_DOC.read_text(encoding='utf-8')
    missing = [code.value for code in ErrorCode if f'`{code.value}`' not in text]
    assert missing == []


def test_unknown_route(client):
    assert_error(client.get('/api/v1/no-such-route'), 404, 'NOT_FOUND')


def test_missing_record(client, keycloak):
    login(client, keycloak)
    body = assert_error(client.patch('/api/v1/launches/999', json={'stage': 1}), 404, 'RECORD_NOT_FOUND')
    assert body['message'] == 'Запись не найдена'


def test_validation_error_names_the_field(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    body = assert_error(client.post('/api/v1/universities', json={'name': '  ', 'city': 'Москва'}), 422, 'VALIDATION_ERROR')
    assert [detail['field'] for detail in body['details']] == ['name']


def test_method_not_allowed(client):
    assert_error(client.delete('/api/v1/universities'), 405, 'METHOD_NOT_ALLOWED')


def test_unexpected_error_hides_internals(app):
    def fail():
        raise RuntimeError('secret internal detail')

    app.add_api_route('/api/v1/test-failure', fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/api/v1/test-failure')
        body = assert_error(response, 500, 'INTERNAL_ERROR')
        assert 'secret internal detail' not in response.text
        assert body['details'] is None


@pytest.mark.parametrize('status, code', [
    (400, 'BAD_REQUEST'),
    (401, 'UNAUTHENTICATED'),
    (403, 'FORBIDDEN'),
    (409, 'CONFLICT'),
    (413, 'PAYLOAD_TOO_LARGE'),
    (415, 'UNSUPPORTED_MEDIA_TYPE'),
    (429, 'RATE_LIMITED'),
    (418, 'BAD_REQUEST'),
])
def test_http_exceptions_map_to_codes(app, status, code):
    def fail():
        raise HTTPException(status_code=status, detail='Своё сообщение', headers={'X-Test': '1'})

    app.add_api_route('/api/v1/test-http-error', fail)
    with TestClient(app) as client:
        response = client.get('/api/v1/test-http-error')
        body = assert_error(response, status, code)
        assert body['message'] == 'Своё сообщение'
        assert response.headers['X-Test'] == '1'


def test_app_error_carries_custom_message_and_details(app):
    def conflict():
        raise AppError(ErrorCode.CONFLICT, 'Договор с таким номером уже есть', [{'field': 'contract_number', 'message': 'Дубликат'}])

    app.add_api_route('/api/v1/test-conflict', conflict)
    with TestClient(app) as client:
        body = assert_error(client.get('/api/v1/test-conflict'), 409, 'CONFLICT')
        assert body['message'] == 'Договор с таким номером уже есть'
        assert body['details'] == [{'field': 'contract_number', 'message': 'Дубликат'}]


def test_unreachable_database_returns_service_unavailable(keycloak):
    app = create_app(make_settings('postgresql+psycopg://crm:unused@127.0.0.1:1/unreachable'), http_client=keycloak.http_client())
    with TestClient(app, raise_server_exceptions=False) as client:
        assert_error(client.get('/api/v1/health'), 503, 'SERVICE_UNAVAILABLE')


@pytest.mark.parametrize('code', list(ErrorCode))
def test_codes_are_stable_identifiers(code):
    assert code.value == code.name
