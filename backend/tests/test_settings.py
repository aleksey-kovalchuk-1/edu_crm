import pytest

from app.main import create_app
from app.settings import SettingsError, load_settings


def test_missing_database_url_fails_fast():
    with pytest.raises(SettingsError, match='DATABASE_URL is not set'):
        load_settings({})


@pytest.mark.parametrize('url', ['sqlite:///./edu_crm.db', 'mysql://user:pass@host/db'])
def test_non_postgres_url_is_rejected(url):
    with pytest.raises(SettingsError, match='Only PostgreSQL'):
        load_settings({'DATABASE_URL': url})


def test_valid_settings_are_normalised():
    settings = load_settings({'DATABASE_URL': ' postgresql+psycopg://u:p@h:5432/db ', 'SEED_DEMO': 'TRUE'})
    assert settings.database_url == 'postgresql+psycopg://u:p@h:5432/db'
    assert settings.seed_demo is True


def test_server_factory_requires_database_url(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(SettingsError):
        create_app()


def test_explicit_non_postgres_url_is_rejected():
    with pytest.raises(SettingsError):
        create_app('sqlite:///./edu_crm.db')
