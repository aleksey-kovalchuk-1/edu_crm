import pytest
from cryptography.fernet import Fernet

from app.main import create_app
from app.settings import SettingsError, database_url_from_environment, load_settings
from helpers import make_settings


def valid_environ(**overrides):
    environ = {
        'DATABASE_URL': 'postgresql+psycopg://u:p@h:5432/db',
        'OIDC_ISSUER': 'http://localhost:8080/auth/realms/edu-crm/',
        'OIDC_INTERNAL_BASE_URL': 'http://keycloak:8080/auth/realms/edu-crm',
        'OIDC_CLIENT_ID': 'edu-crm-api',
        'OIDC_CLIENT_SECRET': 'secret',
        'PUBLIC_BASE_URL': 'http://localhost:8080/',
        'SESSION_ENCRYPTION_KEY': Fernet.generate_key().decode(),
    }
    environ.update(overrides)
    return environ


def test_missing_database_url_fails_fast():
    with pytest.raises(SettingsError, match='DATABASE_URL is not set'):
        load_settings({})


@pytest.mark.parametrize('url', ['sqlite:///./edu_crm.db', 'mysql://user:pass@host/db'])
def test_non_postgres_url_is_rejected(url):
    with pytest.raises(SettingsError, match='Only PostgreSQL'):
        load_settings(valid_environ(DATABASE_URL=url))


def test_missing_authentication_settings_are_listed():
    environ = valid_environ()
    del environ['OIDC_CLIENT_SECRET']
    del environ['SESSION_ENCRYPTION_KEY']
    with pytest.raises(SettingsError, match='OIDC_CLIENT_SECRET, SESSION_ENCRYPTION_KEY'):
        load_settings(environ)


def test_invalid_encryption_key_is_rejected():
    with pytest.raises(SettingsError, match='Fernet key'):
        load_settings(valid_environ(SESSION_ENCRYPTION_KEY='not-a-key'))


@pytest.mark.parametrize('name, value', [
    ('PUBLIC_BASE_URL', 'localhost:8080'),
    ('PUBLIC_BASE_URL', 'http://localhost:8080/app'),
    ('ALLOWED_ORIGINS', 'ftp://files.example'),
    ('SESSION_TTL_HOURS', '0'),
    ('SESSION_TTL_HOURS', 'eight'),
    ('COOKIE_SECURE', 'maybe'),
])
def test_invalid_values_are_rejected(name, value):
    with pytest.raises(SettingsError, match=name):
        load_settings(valid_environ(**{name: value}))


def test_valid_settings_are_normalised():
    settings = load_settings(valid_environ(
        ALLOWED_ORIGINS='http://localhost:5173/, http://127.0.0.1:5173',
        COOKIE_SECURE='false',
        SESSION_TTL_HOURS='4',
    ))
    assert settings.oidc_issuer == 'http://localhost:8080/auth/realms/edu-crm'
    assert settings.public_base_url == 'http://localhost:8080'
    assert settings.callback_url == 'http://localhost:8080/api/v1/auth/callback'
    assert settings.trusted_origins == {'http://localhost:8080', 'http://localhost:5173', 'http://127.0.0.1:5173'}
    assert settings.cookie_secure is False
    assert settings.session_ttl_hours == 4
    assert settings.session_revalidate_seconds == 120


def test_tools_need_only_the_database_url():
    # Migrations and seeding run without login settings (for example from a developer shell).
    assert database_url_from_environment({'DATABASE_URL': ' postgresql+psycopg://u:p@h/db '}) == 'postgresql+psycopg://u:p@h/db'
    with pytest.raises(SettingsError, match='DATABASE_URL is not set'):
        database_url_from_environment({})


def test_cookies_are_secure_by_default():
    assert load_settings(valid_environ()).cookie_secure is True


def test_server_factory_requires_configuration(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(SettingsError):
        create_app()


def test_explicit_non_postgres_url_is_rejected():
    with pytest.raises(SettingsError):
        create_app(make_settings('sqlite:///./edu_crm.db'))
