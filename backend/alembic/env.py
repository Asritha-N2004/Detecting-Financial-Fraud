from alembic import context
from sqlalchemy import create_engine
from app.core.config import settings
from app.database.session import Base
from app.models import tables

target_metadata=Base.metadata
if context.is_offline_mode():
    context.configure(url=settings().database_url,target_metadata=target_metadata,literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
else:
    def run(connection):
        context.configure(connection=connection,target_metadata=target_metadata,render_as_batch=connection.dialect.name=='sqlite')
        with context.begin_transaction(): context.run_migrations()
    supplied=context.config.attributes.get('connection')
    if supplied is not None:
        run(supplied)
    else:
        engine=create_engine(settings().database_url)
        with engine.connect() as connection:
            run(connection)
