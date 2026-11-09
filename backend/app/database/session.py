from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


config=settings()
# Direct connections preserve session advisory locks and schema search paths.
database_url=config.database_url_unpooled or config.database_url
connect_args={'check_same_thread': False} if database_url.startswith('sqlite') else {}
if config.database_schema and database_url.startswith('postgresql'):
    connect_args['options']='-csearch_path='+config.database_schema
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
if database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
