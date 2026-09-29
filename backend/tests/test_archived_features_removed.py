"""The archived customer-data features are removed for good (owner 29.09.2026, D-248; archived by D-235/D-236).

Learner questionnaires, supplier-company screens, the old customer imports and fraud alerts are gone from the code
and the database. What live features use stays: vendor companies and contacts (catalogue, «ИТ-продукты») and course
applications from the customer's JSON (D-247), now without any learner link.
"""
import dataclasses
import importlib

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Base
from app.settings import Settings
from helpers import make_settings

REMOVED_PATHS = ['/api/v1/learners', '/api/v1/vendor-companies', '/api/v1/vendor-contacts',
                 '/api/v1/course-applications', '/api/v1/customer-imports/history', '/api/v1/fraud-alerts']
REMOVED_MODULES = ['learner_routes', 'vendor_routes', 'customer_imports', 'customer_import_routes', 'fraud_alerts',
                   'fraud_fingerprint', 'fraud_routes', 'fraud_rules', 'backfill_fraud_fingerprints']


def test_the_removed_api_is_not_served(database_url):
    app = create_app(make_settings(database_url))
    paths = set(app.openapi()['paths'])
    with TestClient(app) as client:
        for path in REMOVED_PATHS:
            assert path not in paths
            assert client.get(path).status_code == 404, path


@pytest.mark.parametrize('module', REMOVED_MODULES)
def test_the_removed_module_is_gone(module):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f'app.{module}')


def test_the_removed_tables_are_gone_and_live_ones_stay():
    tables = set(Base.metadata.tables)
    assert not tables & {'learners', 'learner_fingerprints', 'fraud_alerts', 'customer_import_batches',
                         'customer_import_row_links'}
    assert {'vendor_companies', 'vendor_contacts', 'course_applications'} <= tables
    assert 'learner_id' not in Base.metadata.tables['course_applications'].columns


def test_the_switch_and_its_keys_are_gone():
    fields = {field.name for field in dataclasses.fields(Settings)}
    assert not fields & {'customer_data_enabled', 'learner_data_encryption_key', 'fraud_match_key'}


def test_migration_0031_refuses_to_drop_tables_that_still_hold_data(empty_database_url):
    from alembic import command
    from sqlalchemy import create_engine, inspect, text

    from app.db_migrate import alembic_config

    config = alembic_config(empty_database_url)
    command.upgrade(config, '0030')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("insert into learners (last_name, first_name, created_at, updated_at) "
                                    "values ('Демо', 'Слушатель', now(), now())"))
        with pytest.raises(RuntimeError, match='learners'):
            command.upgrade(config, '0031')
        with engine.connect() as connection:
            assert 'learners' in inspect(connection).get_table_names()
            assert connection.execute(text('select count(*) from learners')).scalar_one() == 1
            assert connection.execute(text('select version_num from alembic_version')).scalar_one() == '0030'
    finally:
        engine.dispose()
