from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.models import Base
from app.settings import database_url_from_environment

config = context.config
if config.config_file_name is not None and config.attributes.get('configure_logger', True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url():
    # Callers such as tests pass the URL through attributes; this avoids ConfigParser's % interpolation of passwords.
    return config.attributes.get('database_url') or database_url_from_environment()


def run(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline():
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
