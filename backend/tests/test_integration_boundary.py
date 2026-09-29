"""Minimal LMS/website integration boundary (owner 29.09.2026, D-246).

A preliminary internal JSON format only: the customer's contracts do not exist yet (D-233). The contracts endpoint
describes it and is labelled as an internal example; the POST placeholders validate a record and store nothing —
no rows, no raw payload, no workflow, report or analytics effect.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, inspect, select, table

from app.integrations import (
    SCHEMA_VERSION, InboundRecord, LmsAdapter, PreliminaryLmsAdapter, PreliminaryWebsiteAdapter, WebsiteAdapter,
)
from helpers import login

ADMIN = ('crm-admin',)
SUPERADMIN = ('crm-superadmin', 'crm-admin', 'crm-supervisor')


def lms_record(**overrides):
    record = {
        'schema_version': SCHEMA_VERSION,
        'source': 'lms',
        'external_id': 'lms-demo-0001',
        'occurred_at': '2026-09-29T09:30:00+03:00',
        'event_type': 'enrollment',
        'university_ref': 'demo-university',
        'program_ref': 'demo-program',
    }
    record.update(overrides)
    return record


def website_record(**overrides):
    record = lms_record(source='website', external_id='site-demo-0001', event_type='application')
    record.pop('program_ref')
    record.update(overrides)
    return record


def row_counts(database_url):
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            names = inspect(connection).get_table_names()
            return {name: connection.execute(select(func.count()).select_from(table(name))).scalar_one()
                    for name in names}
    finally:
        engine.dispose()


# ---- the record format and adapters ---------------------------------------------------------------------------

def test_a_record_needs_every_required_field_and_the_programme_is_optional():
    record = InboundRecord.model_validate(website_record())
    assert record.program_ref is None
    assert record.occurred_at == datetime(2026, 9, 29, 6, 30, tzinfo=timezone.utc)
    for field in ('schema_version', 'source', 'external_id', 'occurred_at', 'event_type', 'university_ref'):
        broken = lms_record()
        broken.pop(field)
        with pytest.raises(ValueError):
            InboundRecord.model_validate(broken)


@pytest.mark.parametrize('extra', ['raw_payload', 'payload', 'learner_email'])
def test_a_record_refuses_any_field_outside_the_format(extra):
    # No arbitrary raw payload rides along with a record.
    with pytest.raises(ValueError):
        InboundRecord.model_validate(lms_record(**{extra: {'anything': 1}}))


@pytest.mark.parametrize('overrides', [
    {'schema_version': '1'},
    {'source': 'crm'},
    {'occurred_at': '2026-09-29T09:30:00'},  # no time zone
    {'external_id': ''},
    {'external_id': 'x' * 201},
    {'event_type': 'Enrollment Created'},
    {'university_ref': ''},
])
def test_a_record_with_a_bad_value_is_rejected(overrides):
    with pytest.raises(ValueError):
        InboundRecord.model_validate(lms_record(**overrides))


def test_each_adapter_accepts_only_its_own_source():
    assert isinstance(PreliminaryLmsAdapter(), LmsAdapter)
    assert isinstance(PreliminaryWebsiteAdapter(), WebsiteAdapter)
    assert PreliminaryLmsAdapter().parse(lms_record()).external_id == 'lms-demo-0001'
    with pytest.raises(ValueError):
        PreliminaryLmsAdapter().parse(website_record())
    with pytest.raises(ValueError):
        PreliminaryWebsiteAdapter().parse(lms_record())


def test_a_test_fake_can_stand_in_for_an_adapter():
    # The interface is small enough for a test double; real adapters wait for the customer's contract.
    class FakeLms:
        def parse(self, payload):
            return InboundRecord.model_validate(lms_record(external_id=payload['id']))

    assert isinstance(FakeLms(), LmsAdapter)
    assert FakeLms().parse({'id': 'fake-1'}).external_id == 'fake-1'


# ---- GET /integrations/contracts ------------------------------------------------------------------------------

def test_the_contracts_endpoint_is_labelled_as_a_preliminary_internal_example(client, keycloak):
    login(client, keycloak, roles=ADMIN)
    response = client.get('/api/v1/integrations/contracts')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['preliminary'] is True
    assert body['customer_contract'] is False
    assert 'не контракт заказчика' in body['notice']
    assert body['schema_version'] == SCHEMA_VERSION
    assert body['stores_data'] is False
    assert set(body['sources']) == {'lms', 'website'}
    for source, description in body['sources'].items():
        assert description['status'] == 'awaiting_customer_contract'
        assert description['endpoint'] == f'/api/v1/integrations/{source}'
        assert description['examples']
        for example in description['examples']:
            assert example['preliminary'] is True
            InboundRecord.model_validate(example['record'])
            assert example['record']['source'] == source
    assert 'raw_payload' not in response.text
    assert set(body['record_schema']['properties']) == {
        'schema_version', 'source', 'external_id', 'occurred_at', 'event_type', 'university_ref', 'program_ref'}


# ---- POST placeholders ----------------------------------------------------------------------------------------

@pytest.mark.parametrize('source,record', [('lms', lms_record()), ('website', website_record())])
def test_a_valid_record_is_checked_and_nothing_is_stored(client, keycloak, database_url, source, record):
    login(client, keycloak, roles=SUPERADMIN, subject='kc-irina')
    before = row_counts(database_url)
    response = client.post(f'/api/v1/integrations/{source}', json=record)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'validated_only'
    assert body['stored'] is False
    assert body['preliminary'] is True
    assert 'не сохранена' in body['message']
    assert body['record']['external_id'] == record['external_id']
    assert row_counts(database_url) == before


def test_a_record_for_the_other_source_is_rejected(client, keycloak):
    login(client, keycloak, roles=ADMIN)
    response = client.post('/api/v1/integrations/lms', json=website_record())
    assert response.status_code == 422
    assert response.json()['code'] == 'VALIDATION_ERROR'


def test_a_raw_payload_is_rejected_and_not_kept_anywhere(client, keycloak, database_url):
    login(client, keycloak, roles=ADMIN)
    before = row_counts(database_url)
    marker = 'raw-payload-marker-7f3a'
    response = client.post('/api/v1/integrations/website', json=website_record(raw_payload={'note': marker}))
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'raw_payload'
    assert marker not in response.text
    assert row_counts(database_url) == before


@pytest.mark.parametrize('roles', [('crm-user',), ('crm-supervisor',)])
def test_only_administrators_reach_the_boundary(client, keycloak, roles):
    login(client, keycloak, roles=roles)
    assert client.get('/api/v1/integrations/contracts').status_code == 403
    assert client.post('/api/v1/integrations/lms', json=lms_record()).status_code == 403


def test_an_anonymous_request_is_refused(client):
    assert client.get('/api/v1/integrations/contracts').status_code == 401
    assert client.post('/api/v1/integrations/lms', json=lms_record()).status_code == 401


def test_there_is_no_other_integration_route(client):
    paths = [path for path in client.get('/api/openapi.json').json()['paths'] if '/integrations' in path]
    assert sorted(paths) == [
        '/api/v1/integrations/contracts', '/api/v1/integrations/lms', '/api/v1/integrations/website']


def test_swagger_says_the_boundary_is_not_the_customer_contract(client):
    schema = client.get('/api/openapi.json').json()
    for path in ('/api/v1/integrations/contracts', '/api/v1/integrations/lms', '/api/v1/integrations/website'):
        for operation in schema['paths'][path].values():
            assert 'не контракт заказчика' in operation['description']
