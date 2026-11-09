"""Configure a disposable database before importing application modules."""
import os
from pathlib import Path
import tempfile
import pytest

test_directory=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
os.environ['DATABASE_URL']='sqlite:///'+str(Path(test_directory.name)/'test.db').replace('\\','/')
os.environ['JWT_SECRET']='test-only-secret-with-at-least-32-characters'
os.environ['MODEL_PROVIDER']='deterministic'
os.environ['SPECIALIST_PROVIDER']='deterministic'


@pytest.fixture(scope='session',autouse=True)
def close_test_database():
    yield
    from app.database.session import engine
    engine.dispose()
    test_directory.cleanup()
