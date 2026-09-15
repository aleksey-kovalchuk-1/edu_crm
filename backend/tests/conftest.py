import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.models import Base

# Public local-development default from compose.yaml; CI sets TEST_DATABASE_URL explicitly.
DEFAULT_TEST_DATABASE_URL = 'postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/postgres'
TEMPLATE_DATABASE = 'edu_crm_test_template'


def _server_url():
    return make_url(os.environ.get('TEST_DATABASE_URL', DEFAULT_TEST_DATABASE_URL))


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
    # Building the schema once and cloning it per test keeps tests isolated and fast.
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS {TEMPLATE_DATABASE} WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE {TEMPLATE_DATABASE}'))
    engine = create_engine(_server_url().set(database=TEMPLATE_DATABASE))
    Base.metadata.create_all(engine)
    engine.dispose()
    yield TEMPLATE_DATABASE
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS {TEMPLATE_DATABASE} WITH (FORCE)'))


@pytest.fixture
def database_url(admin_engine, template_database):
    name = f'edu_crm_test_{uuid.uuid4().hex[:12]}'
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE {name} TEMPLATE {template_database}'))
    yield _server_url().set(database=name).render_as_string(hide_password=False)
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))
