"""Brings a database to the latest Alembic revision.

Databases created before migrations existed (tables built by create_all, no alembic_version table)
are stamped with the baseline revision first, so their data is kept instead of being recreated.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from .settings import load_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASELINE_REVISION = '0001'
BASELINE_TABLES = frozenset({'universities', 'launches', 'tasks', 'stage_events', 'annual_metrics'})


def alembic_config(database_url, configure_logger=False):
    config = Config(str(BACKEND_DIR / 'alembic.ini'))
    config.attributes['database_url'] = database_url
    config.attributes['configure_logger'] = configure_logger
    return config


def upgrade_database(database_url, configure_logger=False):
    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    config = alembic_config(database_url, configure_logger)
    if 'alembic_version' not in tables and BASELINE_TABLES <= tables:
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, 'head')


if __name__ == '__main__':
    upgrade_database(load_settings().database_url, configure_logger=True)
