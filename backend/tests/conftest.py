import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.db_migrate import upgrade_database

# Public local-development default from compose.yaml; CI sets TEST_DATABASE_URL explicitly.
DEFAULT_TEST_DATABASE_URL = 'postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/postgres'
TEMPLATE_DATABASE = 'edu_crm_test_template'


def _server_url():
    return make_url(os.environ.get('TEST_DATABASE_URL', DEFAULT_TEST_DATABASE_URL))


def _url_for(name):
    return _server_url().set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope='session')
def admin_engine():
    engine = create_engine(_server_url(), isolation_level='AUTOCOMMIT')
    try:
        with engine.connect():
            pass
    except OperationalError as error:
        pytest.exit(
            f'PostgreSQL for tests is unreachable ({error.orig}). '
            'Start it with `docker compose up -d db` or set TEST_DATABASE_URL.',
            returncode=2,
        )
    yield engine
    engine.dispose()


@pytest.fixture(scope='session')
def template_database(admin_engine):
    # Migrating once and cloning per test keeps tests isolated, fast, and on the real migrated schema.
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS {TEMPLATE_DATABASE} WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE {TEMPLATE_DATABASE}'))
    upgrade_database(_url_for(TEMPLATE_DATABASE))
    yield TEMPLATE_DATABASE
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS {TEMPLATE_DATABASE} WITH (FORCE)'))


def _temporary_database(admin_engine, template=None):
    name = f'edu_crm_test_{uuid.uuid4().hex[:12]}'
    clause = f' TEMPLATE {template}' if template else ''
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE {name}{clause}'))
    return name


def _drop_database(admin_engine, name):
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))


@pytest.fixture
def database_url(admin_engine, template_database):
    name = _temporary_database(admin_engine, template_database)
    yield _url_for(name)
    _drop_database(admin_engine, name)


@pytest.fixture
def empty_database_url(admin_engine):
    name = _temporary_database(admin_engine)
    yield _url_for(name)
    _drop_database(admin_engine, name)
