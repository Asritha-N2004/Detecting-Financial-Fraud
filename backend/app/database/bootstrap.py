"""Serialized deployment migrations, using only the host's secret environment."""
from pathlib import Path


def migrate():
    from alembic import command
    from alembic.config import Config
    from app.database.session import engine
    from app.core.config import settings

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'alembic'))
    # A session-level lock serializes worker and API cold-start migrations.
    with engine.connect() as connection:
        postgres = connection.dialect.name == 'postgresql'
        if postgres:
            connection.exec_driver_sql('SELECT pg_advisory_lock(746392180)')
            connection.commit()
        try:
            if postgres and settings().database_schema:
                # Schema names are restricted to identifiers by Settings.
                schema=settings().database_schema
                connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                connection.commit()
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        finally:
            if postgres:
                connection.rollback()
                connection.exec_driver_sql('SELECT pg_advisory_unlock(746392180)')
                connection.commit()
