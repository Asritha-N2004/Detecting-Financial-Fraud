import math
from app.schemas.domain import AssessmentInput, AgentOutput, Issue
from app.agents.analysts import analyze


def evidence_catalog(data: AssessmentInput) -> set[str]:
    refs = {f'statements:{i}' for i in range(len(data.statements))}
    refs |= {f'operational:{i}' for i in range(len(data.operational))}
    if data.prices:
        refs.add(f'prices:0:{len(data.prices)-1}')
    if data.portfolio_weights:
        refs.add('portfolio_weights')
    refs|={f'portfolio_holdings:{i}' for i in range(len(data.portfolio_holdings))}
    if data.debt_schedule: refs.add('debt_schedule')
    return refs


def review(data: AssessmentInput, outputs: dict[str, AgentOutput], aggregate: dict, sensitivity: dict | None = None) -> list[Issue]:
    """Independent rule checker reads original inputs, not just analyst conclusions.

    Numeric recomputation shares the documented engine; it is not independent model validation.
    """
    issues: list[Issue] = []
    refs = evidence_catalog(data)
    def issue(dim, rule, correction, correctable, evidence=None, severity='error'):
        issues.append(Issue(id=f'{dim}:{rule}',agent_id=dim,severity=severity,rule=rule,evidence=evidence or [],correction=correction,correctable=correctable))
    for dim, out in outputs.items():
        if out.llm_interpretation and out.llm_interpretation.status=='completed':
            from app.agents.llm import validate_analysis
            try:
                validate_analysis(out.llm_interpretation.analysis,out)
            except (ValueError,AttributeError):
                issue(dim,'llm_reference_mismatch','Reinterpret using only actual dimension evidence',True)
        if out.llm_interpretation and out.llm_interpretation.status=='failed':
            issue(dim,'llm_unavailable','Review model configuration or provider availability; deterministic analysis remains available',False,severity='warning')
        if out.status != 'completed':
            issue(dim,'missing_dimension','Supply missing source inputs or recover failed execution',out.status=='failed',severity='warning')
        expected = analyze(dim,data)
        if out.score_components!=expected.score_components:
            issue(dim,'component_mismatch','Restore score-component weights and source dependencies from the quantitative rules',True)
        if out.analytics!=expected.analytics:
            issue(dim,'analytics_mismatch','Recompute portfolio matrices or maturity details from the original source',True)
        if (out.score is None) != (expected.score is None) or (out.score is not None and expected.score is not None and not math.isclose(out.score,expected.score,abs_tol=1e-7)):
            issue(dim,'score_mismatch','Recompute score from original inputs',True)
        for key, metric in out.metrics.items():
            canonical = expected.metrics.get(key)
            if canonical and ((metric.value is None)!=(canonical.value is None) or (metric.value is not None and canonical.value is not None and not math.isclose(metric.value,canonical.value,rel_tol=1e-8,abs_tol=1e-10))):
                issue(dim,f'metric_mismatch:{key}','Recompute affected financial metric',True,metric.evidence)
            if metric.value is not None and (not metric.formula or not metric.evidence or any(r not in refs for r in metric.evidence)):
                issue(dim,f'metric_provenance:{key}','Restore formula and valid source references',True,metric.evidence)
        for finding in out.findings:
            if not finding.evidence or any(r not in refs for r in finding.evidence):
                issue(dim,f'unsupported:{finding.id}','Remove unsupported finding or attach actual evidence',True,finding.evidence)
            if any(k not in out.metrics for k in finding.metric_refs):
                issue(dim,f'missing_metric:{finding.id}','Restore referenced quantitative indicator',True,finding.evidence)
        if out.confidence == 'high' and (data.provenance.quality != 'validated' or out.status != 'completed'):
            issue(dim,'excess_confidence','Reduce confidence to match evidence quality',True)
    # Cross-agent shared-ratio agreement is checked separately from each score.
    fin, liq = outputs.get('financial'),outputs.get('liquidity')
    if fin and liq:
        for key in ('current_ratio','quick_ratio','cash_ratio'):
            a,b = fin.metrics.get(key),liq.metrics.get(key)
            if a and b and a.value is not None and b.value is not None and not math.isclose(a.value,b.value,rel_tol=1e-8):
                issue('liquidity',f'contradiction:{key}','Reconcile shared ratio against original statement',True,a.evidence)
    expected_contributions = {d:data.config.weights[d]*o.score for d,o in outputs.items() if o.score is not None and o.status=='completed'}
    if aggregate.get('contributions') != expected_contributions:
        issue('aggregation','weight_mismatch','Reaggregate using configured fixed weights',True)
    if sensitivity is not None:
        from app.financial_engine.sensitivity import risk_sensitivity
        if sensitivity!=risk_sensitivity(outputs,data.config.weights,data.config.sensitivity,data.risk_score_history):
            issue('aggregation','sensitivity_mismatch','Recompute diagnostic sensitivity from validated components and configured weights',True)
    if data.provenance.quality == 'unverified':
        issue('data','unverified_source','Independently verify the supplied financial evidence',False,severity='warning')
    return issues
