import asyncio
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from app.schemas.domain import AssessmentInput, AgentOutput, Issue
from app.agents.analysts import DIMENSIONS, analyze
from app.agents.critic import review
from app.financial_engine.scoring import aggregate
from app.core.config import settings
from app.providers.models import provider
from app.agents.llm import interpret
from app.financial_engine.sensitivity import risk_sensitivity


class WorkflowState(TypedDict, total=False):
    data: AssessmentInput
    outputs: dict[str, AgentOutput]
    executions: list[dict]
    aggregate: dict
    initial_assessment: dict
    issues: list[Issue]
    initial_issues: list[Issue]
    history: list[dict]
    iteration: int
    explanation: dict
    usage: dict
    resume_node: str
    sensitivity: dict


async def execute(dim: str, data: AssessmentInput, attempt_type: str) -> tuple[AgentOutput, dict]:
    start = time.perf_counter()
    error = None
    for attempt in range(settings().agent_retries+1):
        try:
            out = await asyncio.wait_for(asyncio.to_thread(analyze,dim,data),timeout=settings().agent_timeout_seconds)
            # Revalidate even if a future agent adapter returns a plain dict.
            out = AgentOutput.model_validate(out)
            error = None
            break
        except Exception as exc:
            error = type(exc).__name__
    if error:
        out = AgentOutput(agent_id=f'{dim}_analyst',dimension=dim,status='failed',confidence='unavailable',summary='Agent failed; result excluded from scoring',limitations=[error])
    if not error:
        out.llm_interpretation=await interpret(out,data)
        if out.llm_interpretation.status=='failed':
            out.limitations.append('Specialist LLM interpretation failed; deterministic metrics and findings retained')
    out.duration_seconds = time.perf_counter()-start
    record = {'agent_name':out.agent_id,'execution_status':out.status,'execution_time':out.duration_seconds,'error_message':error,'attempts':attempt+1,'attempt_type':attempt_type,'output':out.model_dump()}
    return out,record


async def specialists(state: WorkflowState):
    results = await asyncio.gather(*(execute(d,state['data'],'initial') for d in DIMENSIONS))
    return {'outputs':{o.dimension:o for o,_ in results},'executions':[r for _,r in results],'iteration':0,'history':[]}


def aggregation(state: WorkflowState):
    result = aggregate(state['outputs'],state['data'].config.weights)
    update = {'aggregate':result,'sensitivity':risk_sensitivity(state['outputs'],state['data'].config.weights,state['data'].config.sensitivity,state['data'].risk_score_history)}
    if 'initial_assessment' not in state:
        update['initial_assessment'] = {'aggregate':result,'outputs':{d:o.model_dump() for d,o in state['outputs'].items()}}
    return update


def critic(state: WorkflowState):
    issues = review(state['data'],state['outputs'],state['aggregate'],state.get('sensitivity'))
    update = {'issues':issues}
    if 'initial_issues' not in state:
        update['initial_issues'] = issues
    return update


def route(state: WorkflowState):
    return 'correct' if any(i.correctable for i in state['issues']) and state['iteration'] < state['data'].config.max_reflections else 'explain'


async def correction(state: WorkflowState):
    targets = sorted({i.agent_id for i in state['issues'] if i.correctable and i.agent_id in DIMENSIONS})
    outputs = dict(state['outputs']); executions = list(state['executions'])
    for dim in targets:
        out,record = await execute(dim,state['data'],'targeted_reanalysis')
        outputs[dim] = out; executions.append(record)
    revised = aggregate(outputs,state['data'].config.weights)
    issues = review(state['data'],outputs,revised)
    before_ids = {x.id for x in state['issues']}; after_ids = {x.id for x in issues}
    record = {'iteration_number':state['iteration']+1,'issues_detected':[i.model_dump() for i in state['issues']],
              'corrections_requested':targets,'corrections_completed':sorted(before_ids-after_ids),'unresolved_issues':[i.model_dump() for i in issues],
              'score_before':state['aggregate'],'score_after':revised,'revised_assessments':{d:outputs[d].model_dump() for d in targets},
              'verification_result':'verified' if not issues else 'remaining_issues'}
    return {'outputs':outputs,'executions':executions,'iteration':state['iteration']+1,'history':[*state['history'],record]}


async def explanation(state: WorkflowState):
    agg = state['aggregate']
    summary = f"Evidence coverage {agg['coverage']:.0%}. " + (f"Overall heuristic risk {agg['score']:.1f}/100 ({agg['category']})." if agg['score'] is not None else f"Overall score withheld; possible interval {agg['score_interval'][0]:.1f}–{agg['score_interval'][1]:.1f} because dimensions are incomplete.")
    findings = [f.model_dump() for o in state['outputs'].values() for f in o.findings]
    uncertainty = list(dict.fromkeys(x for o in state['outputs'].values() for x in o.limitations))
    uncertainty += ['Synthetic inputs are demonstration evidence only'] if state['data'].provenance.synthetic else []
    if state.get('sensitivity'):
        uncertainty.append('Shared-input and weight-transfer sensitivity is diagnostic only; no correlation discount changes the saved score')
    interpretations={d:o.llm_interpretation.model_dump(mode='json') for d,o in state['outputs'].items() if o.llm_interpretation and o.llm_interpretation.status!='not_requested'}
    if interpretations:
        uncertainty.append('LLM interpretations pass structural/reference checks only; semantic financial claims remain unverified')
    evidence = sorted({e for f in findings for e in f['evidence']})
    narrative_error = None
    try:
        narrative,usage = await provider().explain({'summary':summary,'findings':findings,'evidence_ids':evidence})
        optional_summary = narrative.summary if settings().model_provider != 'deterministic' else None
    except Exception as exc:
        optional_summary = None; narrative_error = type(exc).__name__; usage = {'provider':settings().model_provider,'tokens':None,'cost_usd':None,'error':narrative_error}
        uncertainty.append('Optional narrative provider failed; deterministic explanation retained')
    # Sum all specialist attempts, including targeted reanalysis, from execution records.
    specialist_usage=[r['output']['llm_interpretation']['usage'] for r in state['executions'] if r.get('output',{}).get('llm_interpretation')]
    token_counts=[usage.get('tokens'),*[u.get('tokens') for u in specialist_usage]]
    combined_usage={'narrative':usage,'specialists':specialist_usage,'tokens':sum(token_counts) if all(x is not None for x in token_counts) else None,
                    'cost_usd':0 if settings().model_provider=='deterministic' and settings().specialist_provider=='deterministic' else None}
    if usage.get('error') or any(x.get('status')=='failed' for x in interpretations.values()):
        combined_usage['error']='One or more model interpretations failed'
    return {'usage':combined_usage,'explanation':{'summary':summary,'optional_unverified_model_summary':optional_summary,'specialist_interpretations':interpretations,
        'findings':[{**f,'reflection_status':'unresolved' if any(i.agent_id==f['dimension'] and i.severity=='error' for i in state['issues']) else 'checked',
                     'critic_comments':[i.model_dump() for i in state['issues'] if i.agent_id==f['dimension']]} for f in findings],
        'risk_drivers':sorted(agg['contributions'].items(),key=lambda x:x[1],reverse=True),
        'limitations':uncertainty,'confidence_statement':'Evidence completeness classification only; neither statistical confidence nor forecast accuracy.',
        'unresolved_issues':[i.model_dump() for i in state['issues']],
        'responsible_use':'Research and decision support. No guaranteed predictions or autonomous investment advice.'}}


def build_graph(on_reflection=None, on_checkpoint=None):
    async def tracked_correction(state):
        if on_reflection:
            on_reflection(state['iteration']+1)
        return await correction(state)
    def tracked(fn, name):
        async def node(state):
            started=time.perf_counter()
            update=await fn(state) if asyncio.iscoroutinefunction(fn) else fn(state)
            execution={'agent_name':name,'execution_status':'completed','execution_time':time.perf_counter()-started,
                       'error_message':None,'attempts':1,'attempt_type':'initial' if not state.get('iteration') else 'verification',
                       'output':{'iteration':state.get('iteration',0),'updated_state_fields':[k for k in update if k!='executions']}}
            update['executions']=[*update.get('executions',state.get('executions',[])),execution]
            return update
        return node
    def reflection_evaluation(state):
        return {} # The bounded decision is evaluated by route from the verified issue set.
    def durable(fn, name):
        async def node(state):
            update=await fn(state) if asyncio.iscoroutinefunction(fn) else fn(state)
            if on_checkpoint:
                merged={**state,**update}
                next_node={'specialists':'aggregate','aggregate':'critic','critic':'reflect','correct':'aggregate','explain':'done'}.get(name)
                if name=='reflect': next_node=route(merged)
                on_checkpoint(next_node,merged)
            return update
        return node
    graph = StateGraph(WorkflowState)
    graph.add_node('specialists',durable(specialists,'specialists'))
    graph.add_node('aggregate',durable(tracked(aggregation,'risk_aggregation'),'aggregate'))
    graph.add_node('critic',durable(tracked(critic,'independent_critic'),'critic'))
    graph.add_node('correct',durable(tracked_correction,'correct'))
    graph.add_node('reflect',durable(tracked(reflection_evaluation,'self_reflection'),'reflect'))
    graph.add_node('explain',durable(tracked(explanation,'decision_explanation'),'explain'))
    graph.add_conditional_edges(START,lambda s:s.get('resume_node','specialists'),{n:n for n in ['specialists','aggregate','critic','reflect','correct','explain']})
    graph.add_edge('specialists','aggregate'); graph.add_edge('aggregate','critic')
    graph.add_edge('critic','reflect')
    graph.add_conditional_edges('reflect',route,{'correct':'correct','explain':'explain'})
    graph.add_edge('correct','aggregate'); graph.add_edge('explain',END)
    return graph.compile()


def serialize_checkpoint(next_node: str, state: WorkflowState, elapsed_seconds: float) -> dict:
    """Versioned JSON only: no pickle, dynamic imports, or serialized callables."""
    from fastapi.encoders import jsonable_encoder
    return {'schema_version':1,'next_node':next_node,'elapsed_seconds':elapsed_seconds,
            'state':jsonable_encoder({k:v for k,v in state.items() if k not in {'data','resume_node'}})}


def restore_checkpoint(data: AssessmentInput, checkpoint: dict) -> WorkflowState:
    if checkpoint.get('schema_version')!=1 or checkpoint.get('next_node') not in {'specialists','aggregate','critic','reflect','correct','explain','done'}:
        raise ValueError('Unsupported workflow checkpoint')
    state=dict(checkpoint['state'])
    state.update(data=data,resume_node=checkpoint['next_node'])
    if 'outputs' in state: state['outputs']={d:AgentOutput.model_validate(o) for d,o in state['outputs'].items()}
    for key in ['issues','initial_issues']:
        if key in state: state[key]=[Issue.model_validate(i) for i in state[key]]
    return state


async def run_workflow(data: AssessmentInput, on_reflection=None, on_checkpoint=None, checkpoint: dict | None = None) -> dict:
    start = time.perf_counter()
    elapsed=checkpoint.get('elapsed_seconds',0) if checkpoint else 0
    initial=restore_checkpoint(data,checkpoint) if checkpoint else {'data':data}
    def save(next_node,state):
        if on_checkpoint: on_checkpoint(serialize_checkpoint(next_node,state,elapsed+time.perf_counter()-start))
    state=initial if checkpoint and checkpoint['next_node']=='done' else await build_graph(on_reflection,save).ainvoke(initial,config={'recursion_limit':30})
    # Explicit serializable state is persisted by the application transaction.
    return {'outputs':{d:o.model_dump() for d,o in state['outputs'].items()},'aggregate':state['aggregate'],'sensitivity':state['sensitivity'],
            'initial_assessment':state['initial_assessment'],'initial_issues':[i.model_dump() for i in state['initial_issues']],
            'reflections':state['history'],'issues':[i.model_dump() for i in state['issues']],
            'verification_status':'verified' if not state['issues'] else 'verified_with_concerns',
            'executions':state['executions'],'explanation':state['explanation'],'usage':state['usage'],
            'duration_seconds':elapsed+time.perf_counter()-start}
