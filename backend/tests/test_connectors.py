"""Mock LMS/CMS connector API: auth, create/update, idempotent redelivery, invalid payloads, and
per-connector data isolation (T-060, D-184-D-187)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import AuditEvent, IntegrationLink, Launch, StatusChange
from helpers import database, login

KEY = 'test-connector-key'


@pytest.fixture
def head(app, keycloak):
    with TestClient(app) as c:
        login(c, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо', email='pavel.demo@demo.local')
        yield c


def create_university(client, name='Северный технологический университет'):
    response = client.post('/api/v1/universities', json={'name': name, 'city': 'Москва', 'contact': ''})
    assert response.status_code == 201, response.text
    return response.json()


def default_workflow(client):
    return next(w for w in client.get('/api/v1/workflows').json() if w['is_default'])


def post_interaction(client, connector, body, key=KEY):
    headers = {'X-Connector-Key': key} if key is not None else {}
    return client.post(f'/api/v1/integrations/{connector}/interactions', json=body, headers=headers)


# ---------- auth ----------

def test_missing_or_wrong_connector_key_is_rejected(client):
    body = {'external_id': 'X-1', 'university': 'Не важно', 'program': 'P', 'product': 'Pr', 'responsible': 'A', 'deadline': '2026-10-01'}
    assert post_interaction(client, 'lms', body, key=None).status_code == 401
    assert post_interaction(client, 'lms', body, key='wrong-key').status_code == 401
    assert client.get('/api/v1/integrations/lms/interactions').status_code == 401


def test_unconfigured_key_rejects_even_the_right_looking_guess(app, keycloak, database_url):
    from app.main import create_app
    from helpers import make_settings

    settings = make_settings(database_url, connector_api_key='')
    with TestClient(create_app(settings, http_client=keycloak.http_client())) as unconfigured:
        response = post_interaction(unconfigured, 'lms', {'external_id': 'X'}, key='')
        assert response.status_code == 401


# ---------- create, update, idempotent redelivery ----------

def test_creates_then_is_idempotent_on_identical_redelivery(app, head, client, database_url):
    university = create_university(head)
    body = {
        'external_id': 'LMS-1001', 'correlation_id': 'corr-1', 'university': university['name'],
        'program': 'Python для начинающих', 'product': 'Учебная среда', 'responsible': 'Иван Петров',
        'deadline': '2026-12-01', 'students': 25,
    }
    created = post_interaction(client, 'lms', body)
    assert created.status_code == 200, created.text
    assert created.json()['action'] == 'created'
    crm_id = created.json()['crm_id']
    assert created.json()['university'] == university['name']
    assert created.json()['responsible'] == 'Иван Петров'

    redelivered = post_interaction(client, 'lms', body)
    assert redelivered.status_code == 200
    assert redelivered.json() == {**created.json(), 'action': 'unchanged'}

    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(Launch).where(Launch.id == crm_id)) == 1
        assert db.scalar(select(func.count()).select_from(IntegrationLink).where(
            IntegrationLink.source == 'lms', IntegrationLink.external_id == 'LMS-1001')) == 1
        # Only the initial status-change row from creation; the identical redelivery added nothing.
        assert db.scalar(select(func.count()).select_from(StatusChange).where(StatusChange.launch_id == crm_id)) == 1


def test_update_changes_fields_and_records_a_status_change(app, head, client, database_url):
    university = create_university(head)
    workflow = default_workflow(head)
    second_status = workflow['statuses'][1]
    created = post_interaction(client, 'lms', {
        'external_id': 'LMS-2002', 'university': university['name'], 'program': 'Java', 'product': 'Курс',
        'responsible': 'Анна', 'deadline': '2026-11-01',
    }).json()

    updated = post_interaction(client, 'lms', {
        'external_id': 'LMS-2002', 'program': 'Java Advanced', 'status': second_status['name'], 'students': 40,
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()['action'] == 'updated'
    assert updated.json()['program'] == 'Java Advanced'
    assert updated.json()['status'] == second_status['name']
    assert updated.json()['students'] == 40
    # University was create-only; a later delivery cannot silently move the interaction elsewhere.
    assert updated.json()['university'] == university['name']

    with database(database_url) as db:
        changes = db.scalars(select(StatusChange).where(StatusChange.launch_id == created['crm_id']).order_by(StatusChange.id)).all()
        assert [c.to_status_id for c in changes][-1] == second_status['id']
        assert len(changes) == 2  # creation + this move

    unchanged = post_interaction(client, 'lms', {'external_id': 'LMS-2002', 'program': 'Java Advanced'})
    assert unchanged.json()['action'] == 'unchanged'


# ---------- invalid payloads ----------

def test_unknown_university_is_a_stable_validation_error(client):
    response = post_interaction(client, 'lms', {
        'external_id': 'LMS-3', 'university': 'Не существует', 'program': 'P', 'product': 'Pr',
        'responsible': 'A', 'deadline': '2026-10-01',
    })
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'university'


def test_missing_required_fields_on_create_lists_every_missing_field(client):
    response = post_interaction(client, 'lms', {'external_id': 'LMS-4'})
    assert response.status_code == 422
    fields = {d['field'] for d in response.json()['details']}
    assert fields == {'university', 'program', 'product', 'responsible', 'deadline'}


def test_unknown_status_name_is_a_stable_validation_error(head, client):
    university = create_university(head)
    post_interaction(client, 'lms', {
        'external_id': 'LMS-5', 'university': university['name'], 'program': 'P', 'product': 'Pr',
        'responsible': 'A', 'deadline': '2026-10-01',
    })
    response = post_interaction(client, 'lms', {'external_id': 'LMS-5', 'status': 'Такого статуса нет'})
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'status'


def test_updating_an_unknown_external_id_requires_full_create_fields(client):
    # No existing link for LMS-999, so this is a create attempt missing everything a create needs.
    response = post_interaction(client, 'lms', {'external_id': 'LMS-999', 'program': 'Только программа'})
    assert response.status_code == 422
    fields = {d['field'] for d in response.json()['details']}
    assert fields == {'university', 'product', 'responsible', 'deadline'}


# ---------- per-connector data isolation ----------

def test_lms_and_cms_with_the_same_external_id_are_independent_records(head, client):
    university = create_university(head)
    body = {
        'external_id': 'SHARED-1', 'university': university['name'], 'program': 'P', 'product': 'Pr',
        'responsible': 'A', 'deadline': '2026-10-01',
    }
    lms = post_interaction(client, 'lms', body).json()
    cms = post_interaction(client, 'cms', {**body, 'program': 'Другая программа'}).json()
    assert lms['crm_id'] != cms['crm_id']
    assert lms['program'] == 'P' and cms['program'] == 'Другая программа'

    # Updating through one connector never touches the other's record for the same external_id.
    post_interaction(client, 'lms', {'external_id': 'SHARED-1', 'program': 'Изменено через LMS'})
    assert client.get(f"/api/v1/integrations/cms/interactions/SHARED-1", headers={'X-Connector-Key': KEY}).json()['program'] == 'Другая программа'


# ---------- outbound ----------

def test_outbound_list_and_single_lookup(head, client):
    university = create_university(head)
    created = post_interaction(client, 'lms', {
        'external_id': 'LMS-OUT-1', 'university': university['name'], 'program': 'P', 'product': 'Pr',
        'responsible': 'A', 'deadline': '2026-10-01',
    }).json()

    listed = client.get('/api/v1/integrations/lms/interactions', headers={'X-Connector-Key': KEY}).json()
    assert any(item['crm_id'] == created['crm_id'] and item['external_id'] == 'LMS-OUT-1' for item in listed)

    single = client.get('/api/v1/integrations/lms/interactions/LMS-OUT-1', headers={'X-Connector-Key': KEY})
    assert single.status_code == 200 and single.json()['crm_id'] == created['crm_id']

    assert client.get('/api/v1/integrations/lms/interactions/no-such-id', headers={'X-Connector-Key': KEY}).status_code == 404


# ---------- audit ----------

def test_inbound_delivery_is_audited_without_the_key_or_extra_personal_data(head, client, database_url):
    university = create_university(head)
    created = post_interaction(client, 'lms', {
        'external_id': 'LMS-AUDIT-1', 'university': university['name'], 'program': 'P', 'product': 'Pr',
        'responsible': 'Секретное Имя', 'deadline': '2026-10-01',
    }).json()

    with database(database_url) as db:
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == 'integration.lms.inbound')).all()
        assert len(events) == 1
        event = events[0]
        assert event.payload == {'source': 'lms', 'external_id': 'LMS-AUDIT-1', 'action': 'created', 'launch_id': created['crm_id']}
        assert KEY not in str(event.payload) and 'Секретное Имя' not in str(event.payload)
        assert event.user_id is None  # no human actor -- the connector is the CRM's own integration, not a session
