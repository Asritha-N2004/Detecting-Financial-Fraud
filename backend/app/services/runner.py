"""Durable database queue, renewable leases, fenced writes, and stage recovery."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, update, and_, or_, func
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.tables import Assessment, AssessmentJob, Execution, Finding, Reflection, CriticReport, Score, Explanation, AuditLog, now
from app.schemas.domain import AssessmentInput
from app.orchestration.workflow import run_workflow

logger=logging.getLogger(__name__)


class LeaseLost(RuntimeError):
    pass


class RuntimeChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class Claim:
    job_id: str
    assessment_id: str
    token: str


def audit(db, org_id, user_id, action, resource_id, metadata=None):
    db.add(AuditLog(org_id=org_id,user_id=user_id,action=action,resource_type='assessment',resource_id=resource_id,metadata_json=metadata or {}))


def db_now(db):
    """Use the database clock for cross-worker lease decisions."""
    timestamp=db.scalar(select(func.current_timestamp()))
    return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp


def runtime_manifest() -> dict:
    from hashlib import sha256
    from app.agents.llm import load_prompt
    from app.agents.analysts import DIMENSIONS
    cfg=settings()
    return {'workflow_version':'4','financial_engine_version':'2','sensitivity_version':'1','specialist_provider':cfg.specialist_provider,
            'specialist_model':cfg.specialist_model or cfg.openai_model,
            'specialist_models':cfg.specialist_models,
            'narrative_provider':cfg.model_provider,'narrative_model':cfg.openai_model,
            'provider_endpoint_sha256':sha256((cfg.openai_base_url or '').encode()).hexdigest(),'agent_retries':cfg.agent_retries,
            'tool_rounds':cfg.llm_max_tool_rounds,'completion_tokens':cfg.llm_max_completion_tokens,
            'prompt_hashes':{d:load_prompt(d)[1] for d in DIMENSIONS} if cfg.specialist_provider!='deterministic' else {}}


def enqueue(db, row: Assessment) -> AssessmentJob:
    """Commit queue entry, status transition and audit in the caller transaction."""
    job=AssessmentJob(assessment_id=row.id,status='queued',max_attempts=settings().job_max_attempts,
                      available_at=db_now(db),runtime_json=runtime_manifest())
    db.add(job)
    audit(db,row.org_id,row.created_by,'job_enqueued',row.id)
    return job


def eligible(timestamp):
    return or_(and_(AssessmentJob.status=='queued',AssessmentJob.available_at<=timestamp),
               and_(AssessmentJob.status=='running',AssessmentJob.lease_expires_at<=timestamp))


def guard(db, claim: Claim, **values):
    timestamp=db_now(db)
    result=db.execute(update(AssessmentJob).where(AssessmentJob.id==claim.job_id,
        AssessmentJob.status=='running',AssessmentJob.lease_token==claim.token,
        AssessmentJob.lease_expires_at>timestamp).values(updated_at=timestamp,**values))
    if result.rowcount!=1:
        raise LeaseLost('Job lease is no longer owned')


def fail_exhausted(assessment_id: str | None = None):
    with SessionLocal() as db:
        timestamp=db_now(db)
        scope=[] if assessment_id is None else [AssessmentJob.assessment_id==assessment_id]
        candidates=list(db.scalars(select(AssessmentJob.id).where(*scope,eligible(timestamp),AssessmentJob.attempts>=AssessmentJob.max_attempts).limit(100)))
        for job_id in candidates:
            changed=db.execute(update(AssessmentJob).where(AssessmentJob.id==job_id,eligible(timestamp),AssessmentJob.attempts>=AssessmentJob.max_attempts).values(status='failed',lease_token=None,lease_expires_at=None,last_error='AttemptLimitExceeded',updated_at=timestamp))
            if changed.rowcount:
                job=db.get(AssessmentJob,job_id);row=db.get(Assessment,job.assessment_id)
                row.status='failed';row.error_message='Durable job exhausted its recovery attempts';row.completed_at=timestamp
                audit(db,row.org_id,row.created_by,'job_attempts_exhausted',row.id)
        db.commit()


def claim_next(assessment_id: str | None = None) -> Claim | None:
    fail_exhausted(assessment_id)
    with SessionLocal() as db:
        timestamp=db_now(db)
        scope=[] if assessment_id is None else [AssessmentJob.assessment_id==assessment_id]
        candidates=list(db.scalars(select(AssessmentJob.id).where(*scope,eligible(timestamp),AssessmentJob.attempts<AssessmentJob.max_attempts).order_by(AssessmentJob.created_at,AssessmentJob.id).limit(20)))
        for job_id in candidates:
            token=str(uuid4())
            changed=db.execute(update(AssessmentJob).where(AssessmentJob.id==job_id,eligible(timestamp),AssessmentJob.attempts<AssessmentJob.max_attempts).values(
                status='running',attempts=AssessmentJob.attempts+1,lease_token=token,
                lease_expires_at=timestamp+timedelta(seconds=settings().job_lease_seconds),heartbeat_at=timestamp,updated_at=timestamp))
            if changed.rowcount!=1:
                db.rollback();continue
            job=db.get(AssessmentJob,job_id)
            if job.runtime_json.get('legacy_adopted'):
                job.runtime_json=runtime_manifest()
            row=db.get(Assessment,job.assessment_id)
            audit(db,row.org_id,row.created_by,'job_claimed',row.id,{'attempt':job.attempts,'resuming':job.checkpoint_json is not None})
            db.commit()
            return Claim(job.id,job.assessment_id,token)
    return None


def renew(claim: Claim):
    with SessionLocal() as db:
        timestamp=db_now(db)
        guard(db,claim,lease_expires_at=timestamp+timedelta(seconds=settings().job_lease_seconds),heartbeat_at=timestamp)
        db.commit()


def checkpoint(claim: Claim, snapshot: dict):
    with SessionLocal() as db:
        guard(db,claim,checkpoint_json=snapshot)
        if db.get(AssessmentJob,claim.job_id).runtime_json!=runtime_manifest():
            raise RuntimeChanged('Worker runtime changed during execution')
        row=db.get(Assessment,claim.assessment_id)
        if snapshot['next_node']=='correct': row.status='reflecting'
        audit(db,row.org_id,row.created_by,'workflow_checkpointed',row.id,{'next_node':snapshot['next_node'],'iteration':snapshot['state'].get('iteration',0)})
        db.commit()


def persist_result(db, row: Assessment, result: dict):
    for record in result['executions']:
        db.add(Execution(assessment_id=row.id,agent_name=record['agent_name'],execution_status=record['execution_status'],execution_time=record['execution_time'],error_message=record['error_message'],payload=record))
        audit(db,row.org_id,row.created_by,'agent_executed',row.id,{'agent':record['agent_name'],'status':record['execution_status']})
    for iteration in result['reflections']:
        db.add(Reflection(assessment_id=row.id,iteration_number=iteration['iteration_number'],payload=iteration))
        audit(db,row.org_id,row.created_by,'reflection_completed',row.id,{'iteration':iteration['iteration_number'],'resolved':iteration['corrections_completed']})
    for finding in result['explanation']['findings']:
        db.add(Finding(assessment_id=row.id,payload=finding))
    db.add(CriticReport(assessment_id=row.id,payload={'initial_issues':result['initial_issues'],'final_issues':result['issues']}))
    db.add(Score(assessment_id=row.id,payload={**result['aggregate'],'sensitivity':result['sensitivity']}))
    db.add(Explanation(assessment_id=row.id,payload=result['explanation']))
    row.result_json=result;row.overall_score=result['aggregate']['score'];row.risk_category=result['aggregate']['category']
    row.status='completed_with_warnings' if result['issues'] or result['usage'].get('error') else 'completed'
    row.completed_at=now();row.error_message=None
    audit(db,row.org_id,row.created_by,'assessment_completed',row.id,{'status':row.status})


def finalize(claim: Claim, result: dict):
    with SessionLocal() as db:
        # The fenced update locks the job through artifact commit. Stale recovery
        # cannot finalize concurrently or duplicate artifacts.
        guard(db,claim,status='succeeded',lease_token=None,lease_expires_at=None,last_error=None)
        if db.get(AssessmentJob,claim.job_id).runtime_json!=runtime_manifest():
            raise RuntimeChanged('Worker runtime changed before finalization')
        row=db.get(Assessment,claim.assessment_id)
        persist_result(db,row,result)
        db.commit()


def release(claim: Claim, error: str, permanent: bool = False, cancelled: bool = False):
    with SessionLocal() as db:
        guard(db,claim)
        job=db.get(AssessmentJob,claim.job_id);row=db.get(Assessment,claim.assessment_id)
        failed=permanent or job.attempts>=job.max_attempts
        job.status='failed' if failed else 'queued'
        job.lease_token=None;job.lease_expires_at=None;job.last_error=error
        job.available_at=db_now(db)+timedelta(seconds=0 if cancelled else settings().job_retry_seconds)
        if failed:
            row.status='failed';row.error_message='Workflow recovery failed ('+error+')';row.completed_at=now()
        audit(db,row.org_id,row.created_by,'job_failed' if failed else 'job_requeued',row.id,{'reason':error,'attempt':job.attempts})
        db.commit()


async def heartbeat(claim: Claim):
    while True:
        await asyncio.sleep(settings().job_lease_seconds/3)
        renew(claim)


async def process(claim: Claim):
    work=None;beat=None
    try:
        with SessionLocal() as db:
            job=db.get(AssessmentJob,claim.job_id);row=db.get(Assessment,claim.assessment_id)
            if job.runtime_json!=runtime_manifest():
                raise RuntimeChanged('Worker runtime differs from queued configuration')
            data=AssessmentInput.model_validate(row.input_json);snapshot=job.checkpoint_json
        renew(claim)
        work=asyncio.create_task(run_workflow(data,on_checkpoint=lambda s:checkpoint(claim,s),checkpoint=snapshot))
        beat=asyncio.create_task(heartbeat(claim))
        done,_=await asyncio.wait([work,beat],return_when=asyncio.FIRST_COMPLETED)
        if beat in done: await beat
        result=await work
        finalize(claim,result)
    except LeaseLost:
        logger.warning('Discarded stale worker assessment=%s',claim.assessment_id)
    except asyncio.CancelledError:
        try: release(claim,'WorkerShutdown',cancelled=True)
        except LeaseLost: pass
        raise
    except Exception as exc:
        logger.error('Job attempt failed assessment=%s type=%s',claim.assessment_id,type(exc).__name__)
        try: release(claim,type(exc).__name__,permanent=isinstance(exc,RuntimeChanged))
        except LeaseLost: pass
    finally:
        for task in [work,beat]:
            if task and not task.done(): task.cancel()
        await asyncio.gather(*(t for t in [work,beat] if t),return_exceptions=True)


async def worker_loop(stop: asyncio.Event):
    while not stop.is_set():
        try:
            claim=claim_next()
            if claim:
                await process(claim)
                continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error('Worker poll failed type=%s',type(exc).__name__)
        try: await asyncio.wait_for(stop.wait(),timeout=settings().worker_poll_seconds)
        except TimeoutError: pass


async def standalone():
    import signal
    if settings().deploy_migrations:
        from app.database.bootstrap import migrate
        await asyncio.to_thread(migrate)
    stop=asyncio.Event()
    task=asyncio.create_task(worker_loop(stop))
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, task.cancel)
        except NotImplementedError:
            pass
    try:
        await task
    except asyncio.CancelledError:
        stop.set()


if __name__=='__main__':
    asyncio.run(standalone())
