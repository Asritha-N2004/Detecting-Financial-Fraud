"""Generate synthetic API response fixtures from the actual Python engine."""
import asyncio,json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
os.environ['MODEL_PROVIDER']='deterministic';os.environ['SPECIALIST_PROVIDER']='deterministic'
from app.providers.synthetic import synthetic
from app.orchestration.workflow import run_workflow
from app.financial_engine.stress_testing import stress
from app.financial_engine.sensitivity import risk_sensitivity
from app.schemas.domain import AssessmentInput,AgentOutput,SensitivityConfig


async def main():
    data=synthetic();result=await run_workflow(data)
    assessment={'id':'fixture-a','entity_id':'fixture-entity','entity_name':data.entity_name,'status':'completed_with_warnings',
        'overall_score':result['aggregate']['score'],'risk_category':result['aggregate']['category'],'synthetic':True,
        'created_at':'2026-11-09T00:00:00Z','error_message':None,'input':data.model_dump(mode='json'),'result':result}
    # The UI only reads provenance here; large uploaded histories have their own
    # schema/API tests and are not duplicated into the component fixture.
    assessment['input']={k:assessment['input'][k] for k in ['provenance','statements','prices']}
    assessment['input']['prices']=[]
    folder=root/'frontend'/'src'/'test'/'fixtures';folder.mkdir(parents=True,exist_ok=True)
    for name,value in [('assessment',assessment),('stress',stress(data,'adverse')),('shortfall',stress(data,'combined_adverse'))]:
        (folder/f'{name}.json').write_text(json.dumps(value,indent=2))
    outputs={d:AgentOutput.model_validate(o) for d,o in result['outputs'].items()}
    custom=risk_sensitivity(outputs,{'credit':.2,'market':.3,'liquidity':.2,'financial':.2,'operational':.1},SensitivityConfig(transfer_steps=[.05]))
    (folder/'custom-sensitivity.json').write_text(json.dumps(custom,indent=2))
    history_file=root/'data'/'synthetic'/'sensitivity_history.json'
    if history_file.exists():
        history=AssessmentInput.model_validate_json(history_file.read_text()).risk_score_history
        (folder/'history-sensitivity.json').write_text(json.dumps(risk_sensitivity(outputs,data.config.weights,history=history),indent=2))
    print('Exported synthetic engine-backed frontend response fixtures')


if __name__=='__main__':asyncio.run(main())
