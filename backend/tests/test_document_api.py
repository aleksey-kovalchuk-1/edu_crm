"""Document upload, quarantine/scan, versioning and short-lived downloads (T-093/T-094; design:
docs/design/file-ingestion-plan.md §5.3; decisions D-155, D-159, D-160).

The malware scan itself never talks to a real ClamAV container in tests: `run_scan()` below invokes
`app.document_jobs.run_document_scan` directly (the same call shape `app.worker.run` makes for a claimed
job) with a `fake_clamd.FakeClamd` injected as `scanner_factory`, exactly as `tests/test_jobs.py` exercises
the queue itself without a real poll loop.
"""
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import jobs
from app.document_jobs import run_document_scan
from app.main import create_app
from app.models import AuditEvent, BackgroundJob, Document, DocumentVersion
from fake_clamd import FakeClamd
from helpers import database, login, make_settings

PDF = b'%PDF-1.4 synthetic test document for T-093'
DOCX = b'PK\x03\x04' + b'synthetic docx payload for T-093' * 4
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


# ---------- fixtures ----------

def create_university(client, name='Северный технологический университет', **extra):
    response = client.post('/api/v1/universities', json={'name': name, 'city': 'Санкт-Петербург', 'contact': '', **extra})
    assert response.status_code == 201, response.text
    return response.json()


def create_launch(client, university=None):
    university = university or create_university(client)
    response = client.post('/api/v1/launches', json={
        'university_id': university['id'], 'program': 'Python', 'product': 'Учебная среда', 'owner': 'Менеджер',
        'students': 30, 'deadline': '2026-10-01',
    })
    assert response.status_code == 201, response.text
    return university, response.json()


def create_contract(client, university=None):
    university = university or create_university(client)
    product = client.post('/api/v1/it-products', json={'vendor': 'РТК ИТ', 'name': 'Учебная среда', 'direction_ids': []})
    assert product.status_code == 201, product.text
    contract = client.post('/api/v1/contracts', json={
        'contract_number': f'Д-{university["id"]}-001', 'university_id': university['id'],
        'it_product_id': product.json()['id'], 'signed_at': '2026-01-15',
    })
    assert contract.status_code == 201, contract.text
    return university, contract.json()


def upload(client, *, entity_type, entity_id, title='Документ', doc_type='other', academic_year='', source='',
           filename='doc.pdf', content=PDF, content_type='application/pdf', document_id=None):
    data = {'entity_type': entity_type, 'entity_id': str(entity_id), 'title': title, 'doc_type': doc_type,
            'academic_year': academic_year, 'source': source}
    if document_id is not None:
        data['document_id'] = str(document_id)
    return client.post('/api/v1/documents', data=data, files={'file': (filename, content, content_type)})


def run_scan(app, database_url, job_id, **clamd_kwargs):
    """Runs the document_scan handler exactly once, the way `app.worker.run` would for a claimed job:
    handler call, then `jobs.finish` records the result on the job row."""
    scanner = FakeClamd(**clamd_kwargs)
    with database(database_url) as db:
        job = db.get(BackgroundJob, job_id)
        result = run_document_scan(db, job, scanner_factory=lambda settings: scanner, settings=app.state.settings)
        jobs.finish(db, job, result=result)
    return scanner, result


def quarantine_files(app):
    return list((Path(app.state.settings.documents_dir) / 'quarantine').iterdir())


def stored_files(app):
    directory = Path(app.state.settings.documents_dir) / 'documents'
    return list(directory.iterdir()) if directory.is_dir() else []


# ---------- upload -> scan -> linked -> download round trip ----------

def test_valid_pdf_upload_scans_clean_and_becomes_downloadable(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)

    response = upload(client, entity_type='launch', entity_id=launch['id'], title='Протокол встречи', doc_type='minutes')
    assert response.status_code == 202, response.text
    body = response.json()
    assert body['state'] == 'quarantined' and body['scan_result'] == 'pending'
    assert body['version_number'] == 1
    assert len(quarantine_files(app)) == 1

    with database(database_url) as db:
        queued = db.get(BackgroundJob, body['job_id'])
        assert queued.kind == 'document_scan' and queued.status == 'queued'
        assert queued.payload == {'document_version_id': body['version_id']}
        upload_event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'document.upload'))
        assert upload_event.correlation_id == response.headers['x-correlation-id']

    scanner, result = run_scan(app, database_url, body['job_id'], verdict='OK')
    assert scanner.instream_calls == 1
    assert result['state'] == 'linked' and result['scan_result'] == 'clean'
    assert quarantine_files(app) == []
    assert len(stored_files(app)) == 1

    link = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link")
    assert link.status_code == 200, link.text
    download = client.get(link.json()['url'])
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers['content-type'] == 'application/pdf'
    assert download.headers['content-disposition'].startswith('attachment;')
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert download.headers['cache-control'] == 'private, no-store'

    with database(database_url) as db:
        download_event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'document.download'))
        assert 'admin_access' not in download_event.payload  # not crm-admin

    versions = client.get(f"/api/v1/documents/{body['document_id']}/versions").json()
    assert [v['state'] for v in versions] == ['linked']
    assert versions[0]['uploaded_by']['full_name'] == 'Анна Демо'

    docs = client.get('/api/v1/documents', params={'entity_type': 'launch', 'entity_id': launch['id']}).json()
    assert len(docs) == 1
    assert docs[0]['title'] == 'Протокол встречи'
    assert docs[0]['latest_version']['state'] == 'linked'


def test_valid_docx_upload_round_trip_on_a_contract(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, contract = create_contract(client)

    response = upload(
        client, entity_type='contract', entity_id=contract['id'], title='Акт передачи', doc_type='act',
        filename='act.docx', content=DOCX, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    assert response.status_code == 202, response.text
    body = response.json()
    run_scan(app, database_url, body['job_id'], verdict='OK')

    link = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").json()
    download = client.get(link['url'])
    assert download.status_code == 200
    assert download.content == DOCX
    assert download.headers['content-type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


# ---------- synchronous content checks (before any scan job exists) ----------

def test_signature_mismatch_is_rejected_before_any_scan_job_is_enqueued(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)

    disguised = upload(client, entity_type='launch', entity_id=launch['id'], filename='fake.pdf', content=PNG, content_type='application/pdf')
    assert disguised.status_code == 415, disguised.text
    assert disguised.json()['code'] == 'UNSUPPORTED_MEDIA_TYPE'

    unsupported_extension = upload(client, entity_type='launch', entity_id=launch['id'], filename='doc.txt', content=PDF, content_type='text/plain')
    assert unsupported_extension.status_code == 415

    empty = upload(client, entity_type='launch', entity_id=launch['id'], filename='empty.pdf', content=b'', content_type='application/pdf')
    assert empty.status_code == 415

    assert quarantine_files(app) == []
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0
        assert db.scalar(select(func.count()).select_from(Document)) == 0


def test_oversized_file_is_rejected(app, client, keycloak, database_url, monkeypatch):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)

    import app.document_routes as document_routes
    monkeypatch.setattr(document_routes, 'MAX_DOCUMENT_BYTES', len(PDF) - 1)
    response = upload(client, entity_type='launch', entity_id=launch['id'])
    assert response.status_code == 413, response.text
    monkeypatch.undo()

    assert quarantine_files(app) == []
    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0


# ---------- scan outcomes ----------

def test_infected_file_is_rejected_and_never_downloadable(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()

    scanner, result = run_scan(app, database_url, body['job_id'], verdict='FOUND', signature='Eicar-Test-Signature')
    assert result['state'] == 'rejected' and result['scan_result'] == 'infected'
    assert quarantine_files(app) == []  # deleted, never stored
    assert stored_files(app) == []

    assert client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").status_code == 404
    forged = client.get(f"/api/v1/documents/versions/{body['version_id']}/download", params={'token': 'x' * 64, 'expires': 9999999999})
    assert forged.status_code == 404

    with database(database_url) as db:
        version = db.get(DocumentVersion, body['version_id'])
        assert version.state == 'rejected' and version.scan_result == 'infected'
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == 'document.scan_infected')).all()
        assert len(events) == 1
        assert events[0].payload['signature'] == 'Eicar-Test-Signature'


def test_scanner_connection_error_fails_closed(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()

    scanner, result = run_scan(app, database_url, body['job_id'], raise_connection_error=True)
    assert result['state'] == 'rejected' and result['scan_result'] == 'error'
    assert quarantine_files(app) == []
    assert stored_files(app) == []
    assert client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").status_code == 404


def test_rerunning_the_scan_job_for_an_already_resolved_version_is_a_no_op(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()
    run_scan(app, database_url, body['job_id'], verdict='OK')
    assert len(stored_files(app)) == 1

    # A duplicate/retried document_scan job for the same version must not re-scan, re-move, or re-transition
    # an already-linked version (defence in depth beyond the job queue's own single-claim guarantee).
    scanner2, result2 = run_scan(app, database_url, body['job_id'], verdict='FOUND', signature='should-not-be-scanned')
    assert result2 == {'state': 'linked', 'scan_result': 'clean', 'already_processed': True}
    assert scanner2.instream_calls == 0
    assert len(stored_files(app)) == 1

    download = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link")
    assert download.status_code == 200  # still linked and downloadable, unaffected by the retried job


# ---------- scope ----------

def assign(head, university_id, *user_ids):
    response = head.put(f'/api/v1/universities/{university_id}/managers', json={'user_ids': list(user_ids)})
    assert response.status_code == 200, response.text
    return response.json()


def test_kam_can_upload_and_download_within_assigned_scope(app, client, keycloak, database_url):
    """The brief's "KAM can upload" requirement: crm-user is not sees_all, but within a university they are
    assigned to (D-141 scope) they can upload, scan, and download a document like any other role."""
    login(client, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо')
    university, launch = create_launch(client)

    settings = make_settings(database_url, documents_dir=app.state.settings.documents_dir)
    with TestClient(create_app(settings, http_client=keycloak.http_client())) as kam:
        me = login(kam, keycloak, roles=('crm-user',), subject='kc-kam', name='Ким Демо', email='kam@demo.local')
        assign(client, university['id'], me['user']['id'])

        body = upload(kam, entity_type='launch', entity_id=launch['id']).json()
        run_scan(app, database_url, body['job_id'], verdict='OK')
        link = kam.get(f"/api/v1/documents/versions/{body['version_id']}/download-link")
        assert link.status_code == 200
        assert kam.get(link.json()['url']).status_code == 200


def test_manager_outside_scope_gets_404_not_403(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',), subject='kc-head', name='Павел Демо')
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()
    run_scan(app, database_url, body['job_id'], verdict='OK')
    link_url = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").json()['url']

    settings = make_settings(database_url, documents_dir=app.state.settings.documents_dir)
    with TestClient(create_app(settings, http_client=keycloak.http_client())) as outsider:
        login(outsider, keycloak, roles=('crm-user',), subject='kc-manager', name='Менеджер Демо', email='manager@demo.local')
        assert outsider.get('/api/v1/documents', params={'entity_type': 'launch', 'entity_id': launch['id']}).status_code == 404
        assert outsider.get(f"/api/v1/documents/{body['document_id']}/versions").status_code == 404
        assert outsider.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").status_code == 404
        assert outsider.get(link_url).status_code == 404
        denied_upload = upload(outsider, entity_type='launch', entity_id=launch['id'])
        assert denied_upload.status_code == 404


def test_document_id_must_belong_to_the_same_entity(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    _, other_launch = create_launch(client, create_university(client, name='Другой университет'))
    first = upload(client, entity_type='launch', entity_id=launch['id']).json()

    mismatched = upload(client, entity_type='launch', entity_id=other_launch['id'], document_id=first['document_id'])
    assert mismatched.status_code == 404


# ---------- short-lived links (D-160) ----------

def test_download_link_ttl_is_enforced_even_with_a_valid_session(app, client, keycloak, database_url, monkeypatch):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()
    run_scan(app, database_url, body['job_id'], verdict='OK')

    import app.document_routes as document_routes
    monkeypatch.setattr(document_routes, 'DOWNLOAD_LINK_TTL_SECONDS', -10)
    expired_link = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").json()
    monkeypatch.undo()

    assert client.get(expired_link['url']).status_code == 404

    # The session itself is still fine: a freshly issued link for the same version works right after.
    fresh_link = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").json()
    assert client.get(fresh_link['url']).status_code == 200


def test_download_rejects_a_forged_token(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()
    run_scan(app, database_url, body['job_id'], verdict='OK')
    link = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link").json()['url']

    tampered = link.replace(link.split('token=')[1][:4], 'zzzz')
    assert client.get(tampered).status_code == 404


# ---------- versioning ----------

def test_new_version_preserves_old_version_row_and_file(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)

    first = upload(client, entity_type='launch', entity_id=launch['id'], title='Смета', doc_type='budget').json()
    run_scan(app, database_url, first['job_id'], verdict='OK')

    second_content = PDF + b' v2'
    second = upload(
        client, entity_type='launch', entity_id=launch['id'], title='Смета', doc_type='budget',
        document_id=first['document_id'], content=second_content,
    ).json()
    assert second['document_id'] == first['document_id']
    assert second['version_number'] == first['version_number'] + 1 == 2
    run_scan(app, database_url, second['job_id'], verdict='OK')

    versions = client.get(f"/api/v1/documents/{first['document_id']}/versions").json()
    assert [v['version_number'] for v in versions] == [1, 2]
    assert [v['state'] for v in versions] == ['linked', 'linked']

    link1 = client.get(f"/api/v1/documents/versions/{first['version_id']}/download-link").json()['url']
    link2 = client.get(f"/api/v1/documents/versions/{second['version_id']}/download-link").json()['url']
    assert client.get(link1).content == PDF
    assert client.get(link2).content == second_content
    assert len(stored_files(app)) == 2

    docs = client.get('/api/v1/documents', params={'entity_type': 'launch', 'entity_id': launch['id']}).json()
    assert len(docs) == 1  # one logical Document, not two
    assert docs[0]['latest_version']['version_number'] == 2

    with database(database_url) as db:
        assert db.scalar(select(func.count()).select_from(Document).where(Document.id == first['document_id'])) == 1
        assert db.scalar(select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id == first['document_id'])) == 2


def test_omitting_document_id_always_creates_a_new_document(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    university, launch = create_launch(client)
    upload(client, entity_type='launch', entity_id=launch['id'], title='Смета', doc_type='budget')
    upload(client, entity_type='launch', entity_id=launch['id'], title='Смета', doc_type='budget')  # same title, no document_id

    docs = client.get('/api/v1/documents', params={'entity_type': 'launch', 'entity_id': launch['id']}).json()
    assert len(docs) == 2  # identity is document_id, never an implicit title match


# ---------- administrator access marker (D-158) ----------

def test_admin_access_is_flagged_separately_in_the_audit_trail(app, client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',))
    university, launch = create_launch(client)
    body = upload(client, entity_type='launch', entity_id=launch['id']).json()
    run_scan(app, database_url, body['job_id'], verdict='OK')

    link = client.get(f"/api/v1/documents/versions/{body['version_id']}/download-link")
    assert link.status_code == 200
    client.get(link.json()['url'])

    with database(database_url) as db:
        link_event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'document.download_link'))
        download_event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'document.download'))
        assert link_event.payload['admin_access'] is True
        assert download_event.payload['admin_access'] is True
