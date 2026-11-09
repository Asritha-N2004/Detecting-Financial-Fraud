"""Controlled fault-recovery ablation; not a financial prediction benchmark."""
import asyncio
import json
import time
from pathlib import Path
from copy import deepcopy
from app.providers.synthetic import synthetic
from app.agents.analysts import analyze,DIMENSIONS
from app.agents.critic import review,evidence_catalog
from app.financial_engine.scoring import aggregate,category
from app.orchestration.workflow import correction


def metrics(data,outputs,detected,resolved,elapsed,reference,mode):
    findings=[f for o in outputs.values() for f in o.findings]
    catalog=evidence_catalog(data)
    supported=sum(bool(f.evidence) and all(e in catalog for e in f.evidence) for f in findings)
    canonical={d:analyze(d,data) for d in outputs}
    comparisons=[]
    for d,out in outputs.items():
        comparisons.append(out.score==canonical[d].score)
        for k,m in out.metrics.items():
            expected=canonical[d].metrics.get(k)
            if expected: comparisons.append(m.value==expected.value)
    score=aggregate(outputs,data.config.weights)['score'] if set(outputs)==set(DIMENSIONS) else None
    return {'numerical_consistency':sum(comparisons)/len(comparisons),'evidence_coverage':supported/len(findings) if findings else 0,
        'unsupported_claim_rate':1-supported/len(findings) if findings else 0,
        'contradiction_detection':int(any('contradiction:' in i.rule for i in detected)),
        'issue_resolution_rate':len(resolved)/len([i for i in detected if i.correctable]) if any(i.correctable for i in detected) else None,
        'classification_consistency':int(category(score)==category(reference)) if score is not None else None,
        'output_completeness':sum(o.status=='completed' for o in outputs.values())/5,
        'processing_seconds':elapsed,'llm_tokens':0,'cost_usd':0,'overall_score':score,
        'detection_eligible':mode in ['critic','reflection']}


async def experiment(scenario,mode,fault):
    start=time.perf_counter();data=synthetic(scenario)
    canonical={d:analyze(d,data) for d in DIMENSIONS}; reference=aggregate(canonical,data.config.weights)['score']
    outputs=deepcopy(canonical if mode!='single' else {'financial':canonical['financial']})
    if fault:
        outputs['financial'].metrics['current_ratio'].value=999
        outputs['financial'].findings[0].evidence=['injected:missing-source']
        if 'market' in outputs: outputs['market'].score=99
    detected=[];resolved=[];history=[]
    if mode in ['critic','reflection']:
        detected=review(data,outputs,aggregate(outputs,data.config.weights))
    if mode=='reflection':
        state={'data':data,'outputs':outputs,'aggregate':aggregate(outputs,data.config.weights),'issues':detected,'executions':[],'iteration':0,'history':[]}
        while any(i.correctable for i in state['issues']) and state['iteration']<data.config.max_reflections:
            state.update(await correction(state));state['aggregate']=aggregate(state['outputs'],data.config.weights)
            state['issues']=review(data,state['outputs'],state['aggregate'])
        outputs=state['outputs'];history=state['history']
        resolved=sorted({x for it in history for x in it['corrections_completed']})
    result=metrics(data,outputs,detected,resolved,time.perf_counter()-start,reference,mode)
    return {'scenario':scenario,'mode':mode,'injected_faults':fault,'metrics':result,'detected':[i.model_dump() for i in detected],'resolved':resolved,'iterations':len(history)}


async def main():
    rows=[]
    for scenario in ['healthy','leveraged','volatile']:
        for fault in [False,True]:
            for mode in ['single','multi','critic','reflection']:
                rows.append(await experiment(scenario,mode,fault))
    root=Path(__file__).resolve().parents[2];out=root/'data'/'evaluation';out.mkdir(parents=True,exist_ok=True)
    config={'seed_by_scenario':{'healthy':17,'leveraged':23,'volatile':31},'max_reflections':3,'cases':24,
        'faults':['financial current ratio overwritten to 999','financial finding assigned missing evidence','market score overwritten to 99'],
        'scope':'Controlled deterministic software fault recovery. The single baseline intentionally has one specialist and cannot emit a full score. This does not estimate real financial predictive accuracy.'}
    (out/'results.json').write_text(json.dumps({'configuration':config,'results':rows},indent=2))
    print(json.dumps({'cases':len(rows),'path':str(out/'results.json'),'fault_recovery':[(r['scenario'],r['metrics']['issue_resolution_rate']) for r in rows if r['mode']=='reflection' and r['injected_faults']]}))


if __name__=='__main__': asyncio.run(main())
