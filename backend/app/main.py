import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from uuid import uuid4
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import Field
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.database.session import get_db, SessionLocal
from app.models.tables import User, Organization, Entity, Assessment, AssessmentJob, Execution, Reflection, Explanation, AuditLog, StressResult, FinancialStatement, MarketData, Portfolio, Asset, now
from app.schemas.domain import StrictModel, AssessmentInput, Provenance, Statement, Price,AgentOutput,SensitivityConfig
from app.schemas.sensitivity import SensitivityRequest
from app.financial_engine.sensitivity import risk_sensitivity
from app.security.auth import hash_password, check_password, token_for, current_user, analyst
from app.services.runner import audit, enqueue, worker_loop, claim_next, process
from app.providers.synthetic import synthetic
from app.services.ingestion import parse_upload
from app.financial_engine.stress_testing import stress, SCENARIOS
from app.providers.market_data import YahooFinanceProvider
from app.schemas.scenarios import StressRequest

logger = logging.getLogger('risk-api')
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    if settings().deploy_migrations:
        from app.database.bootstrap import migrate
        await asyncio.to_thread(migrate)
    # Startup does not invalidate another process's active jobs. The worker
    # recovers expired leases and leaves unexpired leases owned by their worker.
    stop=asyncio.Event()
    worker=asyncio.create_task(worker_loop(stop)) if settings().worker_enabled else None
    try:
        yield
    finally:
        stop.set()
        if worker:
            worker.cancel()
            await asyncio.gather(worker,return_exceptions=True)


app = FastAPI(title='Reflective Financial Risk API',version='1.1.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings().cors_origins.split(','),allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
request_times: dict[str,deque] = defaultdict(deque)


@app.middleware('http')
async def request_controls(request: Request, call_next):
    started=time.monotonic(); request_id=str(uuid4())
    host=request.client.host if request.client else 'unknown'
    bucket=request_times[host]
    while bucket and bucket[0]<started-60: bucket.popleft()
    if len(bucket)>=120:
        return JSONResponse({'error':{'code':'rate_limit','message':'Too many requests'}},status_code=429,headers={'Retry-After':'60'})
    bucket.append(started)
    size=request.headers.get('content-length')
    if size and (not size.isdigit() or int(size)>settings().upload_limit_bytes+100000):
        return JSONResponse({'error':{'code':'payload_too_large','message':'Request body too large'}},status_code=413)
    response=await call_next(request)
    response.headers['X-Request-ID']=request_id
    response.headers['X-Content-Type-Options']='nosniff'
    logger.info('request id=%s method=%s path=%s status=%s ms=%.1f',request_id,request.method,request.url.path,response.status_code,(time.monotonic()-started)*1000)
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error':{'code':str(exc.status_code),'message':exc.detail}},status_code=exc.status_code,headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error':{'code':'validation_error','message':'Input validation failed','details':[{'location':list(e['loc']),'message':e['msg']} for e in exc.errors()]}},status_code=422)


@app.exception_handler(Exception)
async def internal_error(request, exc):
    logger.error('Unhandled request error path=%s type=%s',request.url.path,type(exc).__name__)
    return JSONResponse({'error':{'code':'internal_error','message':'Request failed; contact the administrator with the request context'}},status_code=500)


class Credentials(StrictModel):
    email: str = Field(min_length=3,max_length=254,pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=12,max_length=128)


class Registration(Credentials):
    organization: str = Field(min_length=1,max_length=200)


@app.post('/api/v1/auth/register',status_code=201)
def register(body: Registration,db: Session=Depends(get_db)):
    if len(settings().jwt_secret)<32: raise HTTPException(503,'Configure JWT_SECRET first')
    org=Organization(name=body.organization); db.add(org); db.flush()
    user=User(org_id=org.id,email=body.email.lower(),password_hash=hash_password(body.password),role='admin'); db.add(user)
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'Email already registered') from None
    audit(db,user.org_id,user.id,'user_registered',user.id); db.commit()
    return {'access_token':token_for(user),'token_type':'bearer'}


@app.post('/api/v1/auth/login')
def login(body: Credentials,db: Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower()))
    if not user or not check_password(body.password,user.password_hash): raise HTTPException(401,'Invalid credentials')
    audit(db,user.org_id,user.id,'user_login',user.id); db.commit()
    return {'access_token':token_for(user),'token_type':'bearer'}


def owned(db: Session, assessment_id: str, user: User) -> Assessment:
    row=db.scalar(select(Assessment).where(Assessment.id==assessment_id,Assessment.org_id==user.org_id))
    if not row: raise HTTPException(404,'Assessment not found')
    return row


def serialize(row: Assessment, detail=False):
    result={k:getattr(row,k) for k in ['id','entity_id','assessment_type','status','overall_score','risk_category','model_version','created_at','completed_at','error_message']}
    result['entity_name']=row.input_json['entity_name']; result['synthetic']=row.input_json['provenance']['synthetic']
    if detail: result.update(input=row.input_json,result=row.result_json)
    return result


def create_record(body: AssessmentInput,user: User,db: Session) -> Assessment:
    entity=Entity(org_id=user.org_id,name=body.entity_name,currency=body.provenance.currency); db.add(entity); db.flush()
    row=Assessment(org_id=user.org_id,entity_id=entity.id,created_by=user.id,assessment_type=body.assessment_type,input_json=body.model_dump(mode='json')); db.add(row); db.flush()
    if body.statements: db.add(FinancialStatement(org_id=user.org_id,entity_id=entity.id,payload={'statements':[s.model_dump(mode='json') for s in body.statements],'provenance':body.provenance.model_dump(mode='json')}))
    if body.prices: db.add(MarketData(org_id=user.org_id,entity_id=entity.id,payload={'prices':[p.model_dump(mode='json') for p in body.prices],'provenance':body.provenance.model_dump(mode='json')}))
    if body.portfolio_weights or body.portfolio_holdings:
        weights=[h.weight for h in body.portfolio_holdings] or body.portfolio_weights
        p=Portfolio(org_id=user.org_id,entity_id=entity.id,payload={'weights':weights,'value':body.portfolio_value,'holdings':[h.model_dump(mode='json') for h in body.portfolio_holdings]}); db.add(p); db.flush()
        for i,w in enumerate(weights): db.add(Asset(portfolio_id=p.id,symbol=body.portfolio_holdings[i].symbol if body.portfolio_holdings else (f'SYNTHETIC_COMPONENT_{i+1}' if body.provenance.synthetic else f'UNIDENTIFIED_COMPONENT_{i+1}'),weight=w))
    audit(db,user.org_id,user.id,'assessment_created',row.id); db.commit()
    return row


@app.post('/api/v1/assessments',status_code=201)
def create_assessment(body: AssessmentInput,user: User=Depends(analyst),db: Session=Depends(get_db)):
    return serialize(create_record(body,user,db))


@app.get('/api/v1/assessments')
def list_assessments(offset: int=Query(0,ge=0),limit: int=Query(20,ge=1,le=100),user: User=Depends(current_user),db: Session=Depends(get_db)):
    query=select(Assessment).where(Assessment.org_id==user.org_id)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    return {'items':[serialize(a) for a in db.scalars(query.order_by(Assessment.created_at.desc()).offset(offset).limit(limit))],'total':total,'offset':offset,'limit':limit}


@app.get('/api/v1/assessments/{assessment_id}')
def get_assessment(assessment_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    return serialize(owned(db,assessment_id,user),True)


@app.post('/api/v1/assessments/{assessment_id}/run',status_code=202)
async def run_assessment(assessment_id: str,user: User=Depends(analyst),db: Session=Depends(get_db)):
    row=owned(db,assessment_id,user)
    changed=db.execute(update(Assessment).where(Assessment.id==row.id,Assessment.status=='pending').values(status='running'))
    if changed.rowcount!=1: db.rollback(); raise HTTPException(409,'Only pending assessments can be started')
    enqueue(db,row)
    audit(db,user.org_id,user.id,'assessment_started',row.id); db.commit()
    await request_work(row.id)
    return {'id':row.id,'status':'running'}


async def request_work(assessment_id: str):
    if not settings().request_worker_enabled:
        return
    claim=claim_next(assessment_id)
    if claim:
        try:
            await asyncio.wait_for(process(claim),timeout=settings().request_worker_seconds)
        except TimeoutError:
            # process() handles cancellation by releasing the lease/checkpoint.
            pass


@app.post('/api/v1/assessments/{assessment_id}/work',status_code=202)
async def resume_request_work(assessment_id: str,user: User=Depends(analyst),db: Session=Depends(get_db)):
    row=owned(db,assessment_id,user)
    if not settings().request_worker_enabled:
        raise HTTPException(409,'Request-bound execution is not enabled')
    db.commit()  # Release read transaction before the worker uses its sessions.
    await request_work(row.id)
    return {'id':row.id,'status':'accepted'}


@app.get('/api/v1/assessments/{assessment_id}/agents')
def agents(assessment_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    owned(db,assessment_id,user)
    return [r.payload for r in db.scalars(select(Execution).where(Execution.assessment_id==assessment_id).order_by(Execution.created_at))]


@app.get('/api/v1/assessments/{assessment_id}/job')
def job_status(assessment_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    owned(db,assessment_id,user)
    job=db.scalar(select(AssessmentJob).where(AssessmentJob.assessment_id==assessment_id))
    if not job: raise HTTPException(404,'Assessment has not been queued')
    return {'status':job.status,'attempts':job.attempts,'max_attempts':job.max_attempts,'request_worker_enabled':settings().request_worker_enabled,
            'next_node':job.checkpoint_json.get('next_node') if job.checkpoint_json else 'specialists',
            'heartbeat_at':job.heartbeat_at,'available_at':job.available_at,'last_error':job.last_error,
            'checkpoint_version':job.checkpoint_json.get('schema_version') if job.checkpoint_json else None}


@app.get('/api/v1/assessments/{assessment_id}/reflections')
def reflections(assessment_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    owned(db,assessment_id,user)
    return [r.payload for r in db.scalars(select(Reflection).where(Reflection.assessment_id==assessment_id).order_by(Reflection.iteration_number))]


@app.get('/api/v1/assessments/{assessment_id}/explanations')
def explanations(assessment_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    owned(db,assessment_id,user)
    row=db.scalar(select(Explanation).where(Explanation.assessment_id==assessment_id))
    if not row: raise HTTPException(409,'Explanation is not ready')
    return row.payload


@app.get('/api/v1/assessments/{assessment_id}/sensitivity')
def saved_sensitivity(assessment_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    row=owned(db,assessment_id,user)
    if not row.result_json:raise HTTPException(409,'Sensitivity is not ready')
    if not row.result_json.get('sensitivity'):raise HTTPException(409,'This older assessment has no saved sensitivity; run an exploratory diagnosis')
    return row.result_json['sensitivity']


@app.post('/api/v1/assessments/{assessment_id}/sensitivity')
def exploratory_sensitivity(assessment_id: str,body: SensitivityRequest,user: User=Depends(analyst),db: Session=Depends(get_db)):
    row=owned(db,assessment_id,user)
    if not row.result_json:raise HTTPException(409,'Complete the assessment before exploring sensitivity')
    source=AssessmentInput.model_validate(row.input_json)
    outputs={d:AgentOutput.model_validate(o) for d,o in row.result_json['outputs'].items()}
    weights=body.weights if body.weights is not None else source.config.weights
    report=risk_sensitivity(outputs,weights,SensitivityConfig(transfer_steps=body.transfer_steps),source.risk_score_history)
    audit(db,user.org_id,user.id,'sensitivity_analyzed',row.id,{'weights':weights,'transfer_steps':body.transfer_steps,'category_changes':report['category_changes']})
    db.commit()
    return {**report,'assessment_aggregate':row.result_json['aggregate'],'exploratory':True}


@app.get('/api/v1/assessments/{assessment_id}/audit')
def audit_history(assessment_id: str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),user: User=Depends(current_user),db: Session=Depends(get_db)):
    owned(db,assessment_id,user)
    return [{'id':r.id,'action':r.action,'timestamp':r.timestamp,'metadata':r.metadata_json} for r in db.scalars(select(AuditLog).where(AuditLog.resource_id==assessment_id,AuditLog.org_id==user.org_id).order_by(AuditLog.timestamp).offset(offset).limit(limit))]


@app.post('/api/v1/assessments/{assessment_id}/stress-tests')
def stress_tests(assessment_id: str,body: StressRequest,user: User=Depends(analyst),db: Session=Depends(get_db)):
    row=owned(db,assessment_id,user)
    try: result=stress(AssessmentInput.model_validate(row.input_json),body.scenario,body.model_dump(exclude={'scenario'},exclude_none=True))
    except ValueError as exc: raise HTTPException(422,str(exc)) from None
    db.add(StressResult(assessment_id=row.id,payload=result)); audit(db,user.org_id,user.id,'stress_test_executed',row.id,{'scenario':body.scenario}); db.commit()
    return result


@app.post('/api/v1/data/{kind}')
async def upload(kind: str,file: UploadFile=File(...),user: User=Depends(analyst)):
    if kind not in {'financial-statements','market-data'}: raise HTTPException(404,'Unknown data kind')
    content=await file.read(settings().upload_limit_bytes+1)
    if len(content)>settings().upload_limit_bytes: raise HTTPException(413,'Upload exceeds size limit')
    try: rows=await asyncio.to_thread(parse_upload,content,file.filename or '',kind)
    except Exception as exc: raise HTTPException(422,f'Invalid upload ({type(exc).__name__}); check the documented schema') from None
    # Staged records become durable with the assessment, after cross-file validation.
    return {'rows':rows,'status':'validated_staging','provenance_required':True}


@app.post('/api/v1/demo/{scenario}',status_code=202)
async def demo(scenario: str,user: User=Depends(analyst),db: Session=Depends(get_db)):
    try: data=synthetic(scenario)
    except ValueError: raise HTTPException(404,'Choose healthy, leveraged, or volatile') from None
    row=create_record(data,user,db)
    db.execute(update(Assessment).where(Assessment.id==row.id,Assessment.status=='pending').values(status='running'))
    enqueue(db,row)
    audit(db,user.org_id,user.id,'assessment_started',row.id,{'synthetic':True}); db.commit()
    await request_work(row.id)
    db.refresh(row)
    return serialize(row)


@app.get('/api/v1/health')
def health(db: Session=Depends(get_db)):
    db.execute(select(1))
    return {'status':'ok','version':'1.1.0','narrative_provider':settings().model_provider,
            'specialist_provider':settings().specialist_provider,'worker_enabled':settings().worker_enabled}


class MarketImport(StrictModel):
    symbol: str = Field(pattern=r'^[A-Za-z0-9.^=\-]{1,20}$')
    start: date
    end: date
    currency: str = Field(pattern=r'^[A-Z]{3}$')


@app.post('/api/v1/import/market')
async def import_market(body: MarketImport,user: User=Depends(analyst)):
    try:
        prices,provenance=await asyncio.wait_for(asyncio.to_thread(YahooFinanceProvider().history,body.symbol,body.start,body.end,body.currency),timeout=25)
    except Exception as exc:
        raise HTTPException(502,f'Market provider unavailable or rejected input ({type(exc).__name__}); upload a local dataset instead') from None
    return {'rows':[p.model_dump(mode='json') for p in prices],'provenance':provenance.model_dump(mode='json'),'status':'validated_staging'}
