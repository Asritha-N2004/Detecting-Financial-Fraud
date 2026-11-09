import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from sqlalchemy import select,func
from app.database.session import Base,engine,SessionLocal
from app.models.tables import Organization,User,Entity,Assessment,AssessmentJob,Execution,Explanation,AuditLog
from app.providers.synthetic import synthetic
from app.services import runner
from app.orchestration import workflow
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolated_database():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    yield


def queued(max_attempts=3):
    data=synthetic()
    with SessionLocal() as db:
        org=Organization(name='Recovery org');db.add(org);db.flush()
        user=User(org_id=org.id,email=org.id+'@example.com',password_hash='not-a-login-hash');db.add(user)
        entity=Entity(org_id=org.id,name=data.entity_name,currency='USD');db.add(entity);db.flush()
        row=Assessment(org_id=org.id,entity_id=entity.id,created_by=user.id,assessment_type='company',status='running',input_json=data.model_dump(mode='json'));db.add(row);db.flush()
        job=runner.enqueue(db,row);job.max_attempts=max_attempts;db.commit()
        return row.id


def expire(claim):
    with SessionLocal() as db:
        job=db.get(AssessmentJob,claim.job_id);job.lease_expires_at=runner.db_now(db)-timedelta(seconds=1);db.commit()


def test_concurrent_claim_has_one_owner_and_expired_owner_is_fenced():
    queued()
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:runner.claim_next(),range(4)))
    assert sum(c is not None for c in claims)==1
    owner=next(c for c in claims if c)
    runner.renew(owner)
    assert runner.claim_next() is None
    expire(owner);recovered=runner.claim_next()
    assert recovered and owner.token!=recovered.token
    with pytest.raises(runner.LeaseLost): runner.renew(owner)
    with pytest.raises(runner.LeaseLost): runner.checkpoint(owner,{'schema_version':1})
    with pytest.raises(runner.LeaseLost): runner.finalize(owner,{})
    with pytest.raises(runner.LeaseLost): runner.release(owner,'stale')


def test_snapshot_resume_does_not_repeat_completed_specialists(monkeypatch):
    data=synthetic();saved=[]
    class Crash(BaseException): pass
    def interrupt(snapshot):
        saved.append(json.loads(json.dumps(snapshot)))
        if snapshot['next_node']=='critic': raise Crash()
    with pytest.raises(Crash): asyncio.run(workflow.run_workflow(data,on_checkpoint=interrupt))
    assert saved[-1]['next_node']=='critic'
    async def no_replay(*args): raise AssertionError('completed specialists must not rerun')
    monkeypatch.setattr(workflow,'execute',no_replay)
    result=asyncio.run(workflow.run_workflow(data,checkpoint=saved[-1]))
    assert len(result['executions'])==9
    assert result['aggregate']['score'] is not None


def test_recovery_after_real_process_exit_and_idempotent_finalization():
    assessment_id=queued()
    code='''
import asyncio,os
from app.services import runner
original=runner.checkpoint
def crash(claim,snapshot):
    original(claim,snapshot)
    if snapshot['next_node']=='critic': os._exit(73)
runner.checkpoint=crash
asyncio.run(runner.process(runner.claim_next()))
'''
    first=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert first.returncode==73,first.stderr
    with SessionLocal() as db:
        job=db.scalar(select(AssessmentJob).where(AssessmentJob.assessment_id==assessment_id))
        assert job.checkpoint_json['next_node']=='critic'
        assert job.status=='running'
        job.lease_expires_at=runner.db_now(db)-timedelta(seconds=1);db.commit()
    code='''
import asyncio
from app.services import runner
from app.orchestration import workflow
async def forbidden(*args): raise AssertionError('completed specialist repeated')
workflow.execute=forbidden
asyncio.run(runner.process(runner.claim_next()))
'''
    second=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert second.returncode==0,second.stderr
    with SessionLocal() as db:
        job=db.scalar(select(AssessmentJob).where(AssessmentJob.assessment_id==assessment_id))
        assert job.status=='succeeded' and job.attempts==2
        assert db.get(Assessment,assessment_id).status=='completed_with_warnings'
        assert db.scalar(select(func.count()).select_from(Execution))==9
        assert db.scalar(select(func.count()).select_from(Explanation))==1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='assessment_completed'))==1
    assert runner.claim_next() is None


def test_done_checkpoint_can_finalize_without_repeating_model_or_graph(monkeypatch):
    assessment_id=queued();claim=runner.claim_next()
    asyncio.run(workflow.run_workflow(synthetic(),on_checkpoint=lambda s:runner.checkpoint(claim,s)))
    expire(claim);claim=runner.claim_next()
    monkeypatch.setattr(workflow,'build_graph',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('graph must not repeat')))
    asyncio.run(runner.process(claim))
    with SessionLocal() as db: assert db.get(Assessment,assessment_id).status=='completed_with_warnings'
    with pytest.raises(runner.LeaseLost): runner.finalize(claim,{})


def test_attempt_cap_and_runtime_changes_do_not_loop(monkeypatch):
    assessment_id=queued(max_attempts=1);claim=runner.claim_next();expire(claim)
    assert runner.claim_next() is None
    with SessionLocal() as db: assert db.get(Assessment,assessment_id).status=='failed'
    second=queued();claim=runner.claim_next()
    monkeypatch.setattr(settings(),'specialist_model','changed-configuration')
    asyncio.run(runner.process(claim))
    with SessionLocal() as db:
        assert db.get(Assessment,second).status=='failed'
        assert db.get(AssessmentJob,claim.job_id).last_error=='RuntimeChanged'


def test_shutdown_requeues_owned_work_and_preserves_checkpoint(monkeypatch):
    queued();claim=runner.claim_next();entered=asyncio.Event()
    original=runner.run_workflow
    async def paused(*args,**kwargs):
        def stop_at_stage(snapshot):
            kwargs['on_checkpoint'](snapshot)
            if snapshot['next_node']=='critic': entered.set()
        # Save a complete valid snapshot, then pause before returning result.
        await original(args[0],on_checkpoint=stop_at_stage)
        await asyncio.sleep(100)
    monkeypatch.setattr(runner,'run_workflow',paused)
    async def simulate():
        task=asyncio.create_task(runner.process(claim))
        await asyncio.wait_for(entered.wait(),5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(simulate())
    with SessionLocal() as db:
        job=db.get(AssessmentJob,claim.job_id)
        assert job.status=='queued' and job.checkpoint_json
        assert job.last_error=='WorkerShutdown'


def test_runtime_manifest_contains_no_endpoint_credentials(monkeypatch):
    monkeypatch.setattr(settings(),'openai_base_url','https://user:password@provider.example/v1?token=secret')
    serialized=json.dumps(runner.runtime_manifest())
    assert 'password' not in serialized and 'token=secret' not in serialized


@pytest.mark.parametrize('next_node',['aggregate','critic','reflect','correct','explain','done'])
def test_resume_each_stage_preserves_reflection_bound_and_prior_state(next_node,monkeypatch):
    original=workflow.analyze
    seen=0
    def one_wrong_score(dimension,data):
        nonlocal seen
        result=original(dimension,data)
        if dimension=='market':
            seen+=1
            if seen==1: result.score=99
        return result
    monkeypatch.setattr(workflow,'analyze',one_wrong_score)
    saved=[]
    class Crash(BaseException): pass
    def interrupt(snapshot):
        if snapshot['next_node']==next_node:
            saved.append(snapshot)
            raise Crash()
    with pytest.raises(Crash):asyncio.run(workflow.run_workflow(synthetic(),on_checkpoint=interrupt))
    recovered=asyncio.run(workflow.run_workflow(synthetic(),checkpoint=saved[-1]))
    assert len(recovered['reflections'])==1
    assert recovered['reflections'][0]['corrections_completed']
    assert seen==2 # Initial market result plus precisely one targeted correction.


def test_runtime_change_during_work_prevents_checkpoint_and_finalize(monkeypatch):
    queued();claim=runner.claim_next()
    snapshots=[]
    asyncio.run(workflow.run_workflow(synthetic(),on_checkpoint=snapshots.append))
    monkeypatch.setattr(settings(),'specialist_models',{'credit':'a-new-model'})
    with pytest.raises(runner.RuntimeChanged):runner.checkpoint(claim,snapshots[-1])
    with SessionLocal() as db:
        assert db.get(AssessmentJob,claim.job_id).checkpoint_json is None
    with pytest.raises(runner.RuntimeChanged):runner.finalize(claim,{})
