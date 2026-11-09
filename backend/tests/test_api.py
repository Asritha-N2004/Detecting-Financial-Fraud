import time
import pytest

from fastapi.testclient import TestClient
from app.database.session import Base,engine,SessionLocal
from app.main import app
from app.models.tables import User
from sqlalchemy import select


@pytest.fixture
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def register(c,email='one@example.com'):
    r=c.post('/api/v1/auth/register',json={'email':email,'password':'safe-test-password','organization':'Test Org'})
    assert r.status_code==201,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}


def test_request_worker_completes_without_background_poller(monkeypatch):
    from app.core.config import settings
    config=settings()
    monkeypatch.setattr(config,'worker_enabled',False)
    monkeypatch.setattr(config,'request_worker_enabled',True)
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with TestClient(app) as c:
        h=register(c)
        response=c.post('/api/v1/demo/healthy',headers=h)
        assert response.status_code==202
        row=response.json()
        assert row['status'] in ('completed','completed_with_warnings')
        job=c.get(f"/api/v1/assessments/{row['id']}/job",headers=h).json()
        assert job['status']=='succeeded'
        assert job['request_worker_enabled'] is True
        other=register(c,'other@example.com')
        assert c.post(f"/api/v1/assessments/{row['id']}/work",headers=other).status_code==404
        # Completed work cannot claim or bill a second workflow run.
        assert c.post(f"/api/v1/assessments/{row['id']}/work",headers=h).status_code==202
        assert c.get(f"/api/v1/assessments/{row['id']}/job",headers=h).json()['attempts']==1


def test_lifecycle_and_tenant_isolation(client):
    c=client; h=register(c)
    assert c.get('/api/v1/health').status_code==200
    assert c.get('/api/v1/assessments').status_code==401
    r=c.post('/api/v1/demo/healthy',headers=h); assert r.status_code==202,r.text
    aid=r.json()['id']
    for _ in range(100):
        result=c.get('/api/v1/assessments/'+aid,headers=h).json()
        if result['status'].startswith('completed'): break
        time.sleep(.02)
    assert result['status']=='completed_with_warnings',result
    assert result['overall_score'] is not None
    sensitivity=c.get(f'/api/v1/assessments/{aid}/sensitivity',headers=h).json()
    assert sensitivity['baseline']['score']==result['overall_score']
    assert sensitivity['structural']['pairs'] and sensitivity['empirical']['status']=='unavailable'
    changed=c.post(f'/api/v1/assessments/{aid}/sensitivity',headers=h,json={'weights':{'credit':.2,'market':.3,'liquidity':.2,'financial':.2,'operational':.1},'transfer_steps':[.05]})
    assert changed.status_code==200,changed.text
    assert changed.json()['exploratory'] and changed.json()['assessment_aggregate']['score']==result['overall_score']
    assert c.get(f'/api/v1/assessments/{aid}',headers=h).json()['overall_score']==result['overall_score']
    assert c.post(f'/api/v1/assessments/{aid}/sensitivity',headers=h,json={'weights':{'credit':1}}).status_code==422
    job=c.get(f'/api/v1/assessments/{aid}/job',headers=h).json()
    assert job['status']=='succeeded' and job['next_node']=='done'
    assert 'lease_token' not in job
    executions=c.get(f'/api/v1/assessments/{aid}/agents',headers=h).json()
    assert len(executions)==9
    assert {'risk_aggregation','independent_critic','self_reflection','decision_explanation'} <= {e['agent_name'] for e in executions}
    assert c.get(f'/api/v1/assessments/{aid}/explanations',headers=h).json()['findings']
    assert c.get(f'/api/v1/assessments/{aid}/audit',headers=h).json()
    assert c.post(f'/api/v1/assessments/{aid}/run',headers=h).status_code==409
    assert result['result']['outputs']['market']['analytics']['portfolio']['status']=='completed'
    assert result['result']['outputs']['liquidity']['analytics']['maturity']['buckets']
    stress_response=c.post(f'/api/v1/assessments/{aid}/stress-tests',json={'scenario':'adverse'},headers=h)
    assert stress_response.status_code==200,stress_response.text
    assert stress_response.json()['adverse_projection']['status']=='completed'
    assert stress_response.json()['score_change'] is not None
    assert c.post(f'/api/v1/assessments/{aid}/stress-tests',json={'cash_change':.2},headers=h).status_code==422
    assert c.post(f'/api/v1/assessments/{aid}/stress-tests',json={'asset_shocks':{'unknown':-.2}},headers=h).status_code==422
    from app.models.tables import Asset,StressResult
    with SessionLocal() as db:
        assert set(db.scalars(select(Asset.symbol)))=={'SYNTH_A','SYNTH_B','SYNTH_C'}
        assert db.scalar(select(StressResult)).payload['engine_version']=='2'
    other=register(c,'two@example.com')
    for suffix in ['', '/agents','/audit','/reflections','/explanations','/job','/sensitivity']:
        assert c.get(f'/api/v1/assessments/{aid}'+suffix,headers=other).status_code==404
    assert c.get('/api/v1/assessments',headers=other).json()['total']==0
    assert c.post(f'/api/v1/assessments/{aid}/sensitivity',headers=other,json={}).status_code==404
    assert c.post(f'/api/v1/assessments/{aid}/stress-tests',json={'scenario':'adverse'},headers=other).status_code==404


def test_upload_auth_and_roles(client):
    c=client; h=register(c)
    bad=c.post('/api/v1/auth/login',json={'email':'one@example.com','password':'wrong-password'})
    assert bad.status_code==401
    r=c.post('/api/v1/data/market-data',headers=h,files={'file':('prices.csv',b'date,close\n2025-01-01,100\n2025-01-02,101','text/csv')})
    assert r.status_code==200 and len(r.json()['rows'])==2
    assert c.post('/api/v1/data/market-data',headers=h,files={'file':('bad.exe',b'bad')}).status_code==422
    with SessionLocal() as db:
        user=db.scalar(select(User)); user.role='viewer'; db.commit()
    assert c.post('/api/v1/demo/healthy',headers=h).status_code==403


def test_input_validation_and_missing_operational(client):
    from app.providers.synthetic import synthetic
    h=register(client); raw=synthetic().model_dump(mode='json'); raw['operational']=[]
    r=client.post('/api/v1/assessments',json=raw,headers=h)
    assert r.status_code==201,r.text
    raw['config']['max_reflections']=100
    r=client.post('/api/v1/assessments',json=raw,headers=h)
    assert r.status_code==422 and r.json()['error']['code']=='validation_error'


def test_queued_job_survives_api_shutdown_and_is_recovered_on_restart(monkeypatch):
    from app.core.config import settings
    from app.models.tables import Assessment,AssessmentJob
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    monkeypatch.setattr(settings(),'worker_enabled',False)
    with TestClient(app) as first:
        headers=register(first)
        response=first.post('/api/v1/demo/healthy',headers=headers)
        assert response.status_code==202
        assessment_id=response.json()['id']
        assert first.get(f'/api/v1/assessments/{assessment_id}/job',headers=headers).json()['status']=='queued'
    with SessionLocal() as db:
        assert db.get(Assessment,assessment_id).status=='running'
        assert db.scalar(select(AssessmentJob)).status=='queued'
    monkeypatch.setattr(settings(),'worker_enabled',True)
    with TestClient(app) as second:
        for _ in range(100):
            result=second.get(f'/api/v1/assessments/{assessment_id}',headers=headers).json()
            if result['status'].startswith('completed'):break
            time.sleep(.02)
        assert result['status']=='completed_with_warnings'
        assert second.get(f'/api/v1/assessments/{assessment_id}/job',headers=headers).json()['status']=='succeeded'
