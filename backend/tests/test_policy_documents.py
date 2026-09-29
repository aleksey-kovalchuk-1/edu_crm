"""The two demo policies in «Настройки → Персональные данные» are downloaded from the CRM itself (not from Google
Docs), only by signed-in CRM users, as the exact files recorded in app/policy_documents/SOURCES.md."""
import hashlib
import io
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

import app as app_package
from helpers import login

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    'personal-data-policy': {
        'sha256': 'e51f2b5683c3216dd13724747e2a962b8c9490463a6c4342f43c19c5566c9f9d',
        'filename': 'UniCRM_Политика_обработки_персональных_данных_демо.docx',
        'title': 'Политика UniCRM в отношении обработки персональных данных',
    },
    'information-security-policy': {
        'sha256': '6c71eb58dcbff7a3ca9fdbecc498798bef03d66cca5d06b57ba38beeab293175',
        'filename': 'UniCRM_Политика_информационной_безопасности_демо.docx',
        'title': 'Политика информационной безопасности в организации',
    },
}


def _paragraphs(document_xml):
    # A title can be split across several formatting runs, so read each paragraph's text as Word shows it.
    from xml.etree import ElementTree as ET
    w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    root = ET.fromstring(document_xml)
    return [''.join(t.text or '' for t in p.iter(w + 't')).strip() for p in root.iter(w + 'p')]


def _filename(disposition):
    match = re.search(r"filename\*=utf-8''([^;]+)", disposition, re.I)
    return unquote(match.group(1)) if match else None


@pytest.mark.parametrize('slug', EXPECTED)
def test_a_signed_in_user_downloads_the_recorded_word_file(client, keycloak, slug):
    login(client, keycloak, roles=('crm-user',))
    response = client.get(f'/api/v1/documents/{slug}')
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == DOCX
    assert response.headers['content-disposition'].startswith('attachment;')
    assert _filename(response.headers['content-disposition']) == EXPECTED[slug]['filename']
    assert 'no-store' in response.headers['cache-control']
    assert hashlib.sha256(response.content).hexdigest() == EXPECTED[slug]['sha256']
    with zipfile.ZipFile(io.BytesIO(response.content)) as docx:
        assert docx.testzip() is None
        paragraphs = [p for p in _paragraphs(docx.read('word/document.xml')) if p]
        assert paragraphs[0] == EXPECTED[slug]['title']


@pytest.mark.parametrize('slug', EXPECTED)
def test_an_unauthenticated_request_is_denied(client, slug):
    response = client.get(f'/api/v1/documents/{slug}')
    assert response.status_code == 401
    assert response.content[:2] != b'PK'


def test_an_unknown_document_is_not_found(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    assert client.get('/api/v1/documents/../settings.py').status_code == 404
    assert client.get('/api/v1/documents/unknown').status_code == 404


def test_the_files_ship_inside_the_api_image():
    # backend/Dockerfile copies app/ into the image, and .dockerignore must not drop the documents.
    folder = Path(app_package.__file__).parent / 'policy_documents'
    for slug, expected in EXPECTED.items():
        data = (folder / f'{slug}.docx').read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected['sha256']
    assert 'COPY app ./app' in (ROOT / 'backend/Dockerfile').read_text()
    ignored = (ROOT / 'backend/.dockerignore').read_text().split()
    assert not any(pattern in ignored for pattern in ('*.docx', 'policy_documents', 'app/policy_documents'))
    sources = (folder / 'SOURCES.md').read_text()
    assert all(expected['sha256'] in sources for expected in EXPECTED.values())
