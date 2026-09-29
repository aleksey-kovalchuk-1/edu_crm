import tempfile
from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.models import UserSession, utcnow
from app.settings import Settings
from fake_keycloak import CLIENT_ID, CLIENT_SECRET, INTERNAL_BASE_URL, ISSUER

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()
PUBLIC_BASE_URL = 'http://testserver'


def make_settings(database_url, **overrides):
    values = dict(
        database_url=database_url,
        oidc_issuer=ISSUER,
        oidc_internal_base_url=INTERNAL_BASE_URL,
        oidc_client_id=CLIENT_ID,
        oidc_client_secret=CLIENT_SECRET,
        public_base_url=PUBLIC_BASE_URL,
        session_encryption_key=TEST_ENCRYPTION_KEY,
        cookie_secure=False,
        attachments_dir=tempfile.mkdtemp(prefix='edu-crm-attachments-'),
    )
    values.update(overrides)
    return Settings(**values)


@contextmanager
def database(database_url):
    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


def start_login(client, next_path='/'):
    response = client.get('/api/v1/auth/login', params={'next': next_path}, follow_redirects=False)
    assert response.status_code == 302, response.text
    return {key: values[0] for key, values in parse_qs(urlsplit(response.headers['location']).query).items()}


def finish_login(client, keycloak, query, **identity):
    code = keycloak.issue_code(nonce=query['nonce'], code_challenge=query['code_challenge'], **identity)
    return client.get('/api/v1/auth/callback', params={'code': code, 'state': query['state']}, follow_redirects=False)


def login(client, keycloak, *, roles=('crm-user',), subject='kc-user-1', name='Анна Демо', email='anna.demo@demo.local'):
    """Runs the real browser login flow against the fake Keycloak and prepares the client's CSRF header."""
    response = finish_login(client, keycloak, start_login(client), roles=roles, subject=subject, name=name, email=email)
    assert response.status_code == 302 and response.headers['location'] == '/', response.headers.get('location')
    me = client.get('/api/v1/auth/me')
    assert me.status_code == 200, me.text
    client.headers['X-CSRF-Token'] = me.json()['csrf_token']
    return me.json()


def make_sessions_stale(database_url, seconds=600):
    with database(database_url) as db:
        db.execute(update(UserSession).values(validated_at=utcnow() - timedelta(seconds=seconds)))
        db.commit()
