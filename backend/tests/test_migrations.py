"""Upgrade an actual previous schema containing interrupted application work."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_upgrade_adopts_only_interrupted_assessments_and_recovers(tmp_path):
    backend=Path(__file__).resolve().parents[1]
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(tmp_path/'upgrade.db').replace('\\','/')}
    def run(*args):
        result=subprocess.run([sys.executable,*args],cwd=backend,env=env,capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
        return result.stdout
    run('-m','alembic','upgrade','0001')
    run('-c','''
from app.database.session import SessionLocal
from app.models.tables import Organization,User,Entity,Assessment
from app.providers.synthetic import synthetic
with SessionLocal() as db:
    org=Organization(name='Legacy org');db.add(org);db.flush()
    user=User(org_id=org.id,email='legacy@example.com',password_hash='not-a-login');db.add(user)
    entity=Entity(org_id=org.id,name='Legacy entity',currency='USD');db.add(entity);db.flush()
    for status in ['running','pending','completed']:
        db.add(Assessment(id=status,org_id=org.id,entity_id=entity.id,created_by=user.id,assessment_type='company',status=status,input_json=synthetic().model_dump(mode='json')))
    db.commit()
''')
    run('-m','alembic','upgrade','head')
    output=run('-c','''
import asyncio,json
from sqlalchemy import select,func
from app.database.session import SessionLocal
from app.models.tables import Assessment,AssessmentJob
from app.services import runner
with SessionLocal() as db:
    assert db.scalar(select(func.count()).select_from(AssessmentJob))==1
    assert db.scalar(select(AssessmentJob)).runtime_json['legacy_adopted'] is True
asyncio.run(runner.process(runner.claim_next()))
with SessionLocal() as db:
    print(json.dumps({'recovered':db.get(Assessment,'running').status,'pending':db.get(Assessment,'pending').status,'completed':db.get(Assessment,'completed').status,'job':db.scalar(select(AssessmentJob)).status}))
''')
    assert json.loads(output)=={'recovered':'completed_with_warnings','pending':'pending','completed':'completed','job':'succeeded'}
    assert 'No new upgrade operations detected' in run('-m','alembic','check')
