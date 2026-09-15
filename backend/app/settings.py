import os
from dataclasses import dataclass

LOCAL_EXAMPLE_URL = 'postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/edu_crm'


class SettingsError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    seed_demo: bool


def validate_database_url(url):
    url = (url or '').strip()
    if not url:
        raise SettingsError(f'DATABASE_URL is not set. Example for local development: {LOCAL_EXAMPLE_URL}')
    if not url.startswith('postgresql'):
        raise SettingsError('Only PostgreSQL is supported: DATABASE_URL must start with "postgresql"')
    return url


def load_settings(environ=None):
    environ = os.environ if environ is None else environ
    return Settings(
        database_url=validate_database_url(environ.get('DATABASE_URL')),
        seed_demo=environ.get('SEED_DEMO', 'false').strip().lower() == 'true',
    )
