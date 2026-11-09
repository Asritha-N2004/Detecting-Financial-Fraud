from sqlalchemy import create_engine, inspect
from app.core.config import Settings


def test_marketplace_url_selects_psycopg():
    for scheme in ('postgres', 'postgresql'):
        config = Settings(_env_file=None, database_url=f'{scheme}://u:p@host/db?sslmode=require')
        assert config.database_url == 'postgresql+psycopg://u:p@host/db?sslmode=require'


def test_deployment_bootstrap_is_repeatable(tmp_path, monkeypatch):
    from app.database import session
    from app.database.bootstrap import migrate
    engine = create_engine('sqlite:///' + str(tmp_path / 'migration.db'))
    monkeypatch.setattr(session, 'engine', engine)
    migrate()
    migrate()
    assert 'assessment_jobs' in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('select version_num from alembic_version').scalar() == '0002'
    engine.dispose()
