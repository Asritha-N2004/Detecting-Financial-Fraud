"""Evidence-first deterministic specialists, independent of narrative providers."""
from app.schemas.domain import AssessmentInput, AgentOutput, Finding, Metric, ScoreComponent
from app.financial_engine.sensitivity import RULE_INPUTS
from app.financial_engine.ratios import ratios
from app.financial_engine.market_risk import market_metrics
from app.financial_engine.credit_risk import altman_z
from app.financial_engine.portfolio_risk import portfolio_risk
from app.financial_engine.liquidity_risk import maturity_analysis

DIMENSIONS = ['financial', 'credit', 'market', 'liquidity', 'operational']


def analyze(dimension: str, data: AssessmentInput) -> AgentOutput:
    ref = f'statements:{len(data.statements)-1}'
    metrics = ratios(data.statements[-1], ref) if data.statements else {}
    limitations = ['Illustrative rule thresholds; not industry-calibrated', 'Confidence describes evidence completeness, not statistical certainty']
    selected: dict[str, Metric] = {}
    components: list[tuple[str, float]] = []
    # Scores are monotonic, documented threshold mappings, never random or LLM numbers.
    def higher_bad(key: str, low: float, high: float):
        m = selected.get(key)
        if m and m.value is not None:
            components.append((key, min(100, max(0, (m.value-low)/(high-low)*100))))
    def lower_bad(key: str, good: float, bad: float):
        m = selected.get(key)
        if m and m.value is not None:
            components.append((key, min(100, max(0, (good-m.value)/(good-bad)*100))))
    required: list[str] = []
    analytics={}
    if dimension == 'financial':
        selected = metrics
        required = ['debt_to_assets','net_margin','return_on_assets']
        higher_bad('debt_to_assets', .2,.8); lower_bad('net_margin', .15,-.1); lower_bad('return_on_assets', .1,-.05)
        if len(data.statements) > 1:
            previous = data.statements[-2].revenue
            current = data.statements[-1].revenue
            selected['revenue_growth'] = Metric(value=current/previous-1 if current is not None and previous and previous>0 else None, formula='latest_revenue / previous_revenue - 1', evidence=[ref,f'statements:{len(data.statements)-2}'], assumptions=['Reported periods compared without annualization'])
    elif dimension == 'credit':
        required = ['debt_to_equity','interest_coverage','debt_service_coverage']
        selected = {k:metrics[k] for k in required if k in metrics}
        if data.statements:
            selected['altman_z'] = altman_z(data.statements[-1],data.public_manufacturer,ref)
            if data.statements[-1].equity is not None and data.statements[-1].equity <= 0:
                selected['debt_to_equity'] = Metric(value=None,formula='total_debt / equity',evidence=[ref],limitation='Nonpositive equity: leverage ratio undefined; severe distress flag')
                components.append(('nonpositive_equity',100))
        higher_bad('debt_to_equity',.5,3); lower_bad('interest_coverage',5,1); lower_bad('debt_service_coverage',2,.5)
        limitations.append('Probability of default withheld: no validated calibrated model or representative labeled training set')
    elif dimension == 'market':
        if data.portfolio_holdings or data.assessment_type=='portfolio':
            report=portfolio_risk(data);selected=report['metrics']
            analytics['portfolio']={k:v for k,v in report.items() if k!='metrics'}
            limitations+=report['limitations']
        else:
            selected = market_metrics(data.prices,data.config.confidence,data.config.holding_days)
        required = ['annualized_volatility','historical_var','maximum_drawdown']
        higher_bad('annualized_volatility',.1,.6); higher_bad('historical_var',.005,.08); higher_bad('maximum_drawdown',.05,.5)
        if data.portfolio_weights and not data.portfolio_holdings:
            selected['concentration_hhi'] = Metric(value=sum(w*w for w in data.portfolio_weights),formula='sum(portfolio_weight ** 2)',evidence=['portfolio_weights'],assumptions=['Long-only weights; no constituent returns supplied'])
        if not data.portfolio_holdings:
            limitations.append('No constituent covariance evidence; standalone asset history does not establish portfolio diversification')
        tail = selected.get('tail_observations')
        if tail and tail.value < 20:
            limitations.append('Fewer than 20 tail observations: tail estimate is especially uncertain')
    elif dimension == 'liquidity':
        required = ['current_ratio','quick_ratio','cash_ratio','operating_cash_flow_ratio']
        selected = {k:metrics[k] for k in [*required,'working_capital'] if k in metrics}
        lower_bad('current_ratio',2,.5); lower_bad('quick_ratio',1.5,.3); lower_bad('cash_ratio',.5,.05); lower_bad('operating_cash_flow_ratio',.5,-.1)
        if data.statements:
            s = data.statements[-1]
            selected['cash_after_30pct_contraction'] = Metric(value=s.cash*.7 if s.cash is not None else None,formula='cash * 0.7',unit=s.currency,evidence=[ref],assumptions=['Hypothetical 30% cash contraction'])
        report=maturity_analysis(data)
        selected.update(report['metrics'])
        analytics['maturity']={k:v for k,v in report.items() if k!='metrics'}
        limitations+=report['limitations']
    elif dimension == 'operational':
        for i,indicator in enumerate(data.operational):
            key = f'indicator_{i}'
            selected[key] = Metric(value={'low':20,'moderate':50,'high':85}[indicator.severity],formula='qualitative severity mapping: low=20, moderate=50, high=85',unit='heuristic score',evidence=[f'operational:{i}'],assumptions=['User-reported evidence; not independently corroborated'])
            components.append((key,selected[key].value))
        if not data.operational:
            limitations.append('No operational evidence; absence of incidents cannot establish low risk')
    else:
        raise ValueError(f'Unknown dimension {dimension}')
    missing = [k for k in required if k not in selected or selected[k].value is None]
    complete = bool(components) and not missing
    score = sum(x[1] for x in components)/len(components) if complete else None
    if missing:
        limitations.append('Required scoring inputs missing: '+', '.join(missing))
    score_components=[ScoreComponent(id=f'{dimension}:{key}',metric_refs=[key] if key in selected else [],
        input_fields=RULE_INPUTS.get(key,[f'operational:{key}:severity'] if dimension=='operational' else []),
        evidence=selected[key].evidence if key in selected else [ref],score=value,
        within_dimension_weight=1/len(components) if complete else 0,included=complete) for key,value in components]
    findings = []
    for key, component in components:
        refs = selected[key].evidence if key in selected else [ref]
        findings.append(Finding(id=f'{dimension}:{key}',agent_id=f'{dimension}_analyst',dimension=dimension,
            claim=f'{key.replace("_"," ")}: rule contribution {component:.1f}/100; '+('elevated' if component>=65 else 'monitor' if component>=35 else 'lower observed pressure'),
            evidence=refs,metric_refs=[key] if key in selected else [],
            monitoring_action=f'Validate the source and monitor {key.replace("_"," ")} at the next reporting period.',assumptions=['Rule contribution is not a probability']))
    # Supplementary maturity evidence informs monitoring without silently changing
    # historical score weights or introducing uncalibrated extra score terms.
    if dimension=='liquidity' and data.debt_schedule:
        gap=selected['peak_scheduled_funding_gap']
        due=selected['principal_due_365d']
        findings.append(Finding(id='liquidity:debt_maturity',agent_id='liquidity_analyst',dimension='liquidity',
            claim=f'Dated principal due within 365 days: {due.value:.2f} {data.provenance.currency}; peak supplied-flow funding gap: '+(f'{gap.value:.2f}' if gap.value is not None else 'unavailable'),
            evidence=due.evidence,metric_refs=['principal_due_365d','peak_scheduled_funding_gap'],
            monitoring_action='Reconcile the maturity schedule and verify receipts and funding before the earliest cash shortfall.',assumptions=report['assumptions']))
    return AgentOutput(agent_id=f'{dimension}_analyst', dimension=dimension,status='completed' if complete else 'incomplete',score=score,analytics=analytics,score_components=score_components,
                       confidence='moderate' if complete else 'low' if components else 'unavailable',metrics=selected,findings=findings,limitations=limitations,
                       summary=f'{dimension.capitalize()} analysis: '+(f'{score:.1f}/100 heuristic risk' if score is not None else 'insufficient evidence for a score'))
