from datetime import date, datetime, timezone
from typing import Literal
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Provenance(StrictModel):
    provider: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=300)
    synthetic: bool
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    quality: Literal['validated', 'unverified'] = 'unverified'


class Statement(StrictModel):
    period: date
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    current_assets: float | None = Field(None, ge=0)
    inventory: float | None = Field(None, ge=0)
    cash: float | None = Field(None, ge=0)
    current_liabilities: float | None = Field(None, ge=0)
    total_assets: float | None = Field(None, ge=0)
    total_liabilities: float | None = Field(None, ge=0)
    total_debt: float | None = Field(None, ge=0)
    equity: float | None = None
    revenue: float | None = Field(None, ge=0)
    cost_of_goods: float | None = Field(None, ge=0)
    operating_income: float | None = None
    net_income: float | None = None
    interest_expense: float | None = Field(None, ge=0)
    operating_cash_flow: float | None = None
    retained_earnings: float | None = None
    market_equity: float | None = Field(None, ge=0)
    debt_due_12m: float | None = Field(None, ge=0)
    annual_debt_service: float | None = Field(None, ge=0)
    reporting_days: int = Field(365,ge=1,le=366)

    @model_validator(mode='after')
    def consistency(self):
        if self.current_assets is not None:
            if self.cash is not None and self.cash > self.current_assets:
                raise ValueError('Cash exceeds current assets')
            if self.inventory is not None and self.inventory > self.current_assets:
                raise ValueError('Inventory exceeds current assets')
        if self.total_assets is not None and self.current_assets is not None and self.current_assets > self.total_assets:
            raise ValueError('Current assets exceed total assets')
        if all(x is not None for x in [self.total_assets, self.total_liabilities, self.equity]):
            if not math.isclose(self.total_assets, self.total_liabilities + self.equity, rel_tol=.01, abs_tol=.01):
                raise ValueError('Balance sheet does not balance within 1%')
        return self


class Price(StrictModel):
    date: date
    close: float = Field(gt=0)
    benchmark: float | None = Field(None, gt=0)


class OperationalIndicator(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    severity: Literal['low', 'moderate', 'high']
    evidence: str = Field(min_length=1, max_length=1000)


class PortfolioHolding(StrictModel):
    symbol: str = Field(pattern=r'^[A-Za-z0-9_.^=\-]{1,30}$')
    weight: float = Field(gt=0,le=1)
    provenance: Provenance
    prices: list[Price] = Field(min_length=1,max_length=10000)

    @model_validator(mode='after')
    def price_dates(self):
        dates=[p.date for p in self.prices]
        if dates!=sorted(set(dates)) or any(d>date.today() for d in dates):
            raise ValueError('Constituent dates must be unique, ascending and historical')
        return self


class DebtPayment(StrictModel):
    id: str = Field(min_length=1,max_length=80)
    due_date: date
    principal: float = Field(ge=0)
    interest: float = Field(ge=0)
    rate_type: Literal['fixed','floating','unknown'] = 'unknown'


class OperatingCashFlow(StrictModel):
    id: str = Field(min_length=1,max_length=80)
    date: date
    inflow: float = Field(ge=0)
    outflow: float = Field(ge=0)


class DebtSchedule(StrictModel):
    as_of: date
    provenance: Provenance
    complete: bool = False
    payments: list[DebtPayment] = Field(default_factory=list,max_length=1000)
    operating_flows: list[OperatingCashFlow] = Field(default_factory=list,max_length=1000)
    operating_flows_complete: bool = False
    operating_flows_through: date | None = None

    @model_validator(mode='after')
    def validate_schedule(self):
        if self.as_of>date.today(): raise ValueError('Debt schedule as_of must be historical')
        if self.operating_flows_complete and (self.operating_flows_through is None or self.operating_flows_through<self.as_of):
            raise ValueError('Complete operating flows require an explicit coverage-through date')
        if self.operating_flows_through and any(f.date>self.operating_flows_through for f in self.operating_flows):
            raise ValueError('Operating flows extend beyond the declared coverage date')
        for rows,field in [(self.payments,'due_date'),(self.operating_flows,'date')]:
            dates=[getattr(r,field) for r in rows]
            if dates!=sorted(dates) or any(d<self.as_of for d in dates):
                raise ValueError('Scheduled flows must be ascending and not before as_of')
            if len({r.id for r in rows})!=len(rows): raise ValueError('Scheduled flow IDs must be unique')
        return self


DEFAULT_WEIGHTS = {'credit': .25, 'market': .25, 'liquidity': .20, 'financial': .20, 'operational': .10}


class SensitivityConfig(StrictModel):
    transfer_steps: list[float] = Field(default_factory=lambda:[.05,.10],min_length=1,max_length=3)

    @field_validator('transfer_steps')
    @classmethod
    def valid_steps(cls, value):
        if value!=sorted(set(value)) or any(not math.isfinite(v) or not 0<v<=.25 for v in value):
            raise ValueError('Weight transfer steps must be unique ascending fractions in (0,.25]')
        return value


class RiskScoreObservation(StrictModel):
    date: date
    scores: dict[str,float | None]

    @field_validator('scores')
    @classmethod
    def valid_scores(cls,value):
        if not set(value).issubset(DEFAULT_WEIGHTS) or any(v is not None and (not math.isfinite(v) or not 0<=v<=100) for v in value.values()):
            raise ValueError('History requires known dimensions and scores from 0 to 100 or null')
        return value


class RiskScoreHistory(StrictModel):
    entity_name: str = Field(min_length=1,max_length=200)
    model_version: Literal['rules-2.0']
    holding_days: int = Field(ge=1,le=60)
    confidence: float = Field(gt=.5,lt=1)
    provenance: Provenance
    observations: list[RiskScoreObservation] = Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def valid_dates(self):
        dates=[r.date for r in self.observations]
        if dates!=sorted(set(dates)) or any(d>date.today() for d in dates):
            raise ValueError('Score history dates must be unique, ascending and historical')
        return self


class AnalysisConfig(StrictModel):
    confidence: float = Field(.95, gt=.5, lt=1)
    holding_days: int = Field(1, ge=1, le=60)
    max_reflections: int = Field(3, ge=0, le=3)
    weights: dict[str, float] = Field(default_factory=lambda: DEFAULT_WEIGHTS.copy())
    sensitivity: SensitivityConfig = Field(default_factory=SensitivityConfig)

    @field_validator('weights')
    @classmethod
    def weights_valid(cls, value):
        if set(value) != set(DEFAULT_WEIGHTS) or any(not math.isfinite(x) or x < 0 for x in value.values()) or not math.isclose(sum(value.values()), 1):
            raise ValueError('Weights must contain all five dimensions, be nonnegative, and sum to 1')
        return value


class AssessmentInput(StrictModel):
    entity_name: str = Field(min_length=1, max_length=200)
    assessment_type: Literal['company', 'portfolio'] = 'company'
    provenance: Provenance
    statements: list[Statement] = Field(default_factory=list, max_length=30)
    prices: list[Price] = Field(default_factory=list, max_length=10000)
    operational: list[OperationalIndicator] = Field(default_factory=list, max_length=100)
    portfolio_weights: list[float] = Field(default_factory=list, max_length=100)
    portfolio_holdings: list[PortfolioHolding] = Field(default_factory=list,max_length=20)
    portfolio_value: float | None = Field(None,gt=0)
    debt_schedule: DebtSchedule | None = None
    risk_score_history: RiskScoreHistory | None = None
    public_manufacturer: bool = False
    config: AnalysisConfig = Field(default_factory=AnalysisConfig)

    @model_validator(mode='after')
    def validate_data(self):
        for rows in [self.statements, self.prices]:
            dates = [r.period if isinstance(r, Statement) else r.date for r in rows]
            if dates != sorted(set(dates)):
                raise ValueError('Dates must be unique and ascending')
            if any(d > date.today() for d in dates):
                raise ValueError('Future observations are not allowed')
        if any(s.currency != self.provenance.currency for s in self.statements):
            raise ValueError('Mixed currencies require explicit conversion before ingestion')
        if self.portfolio_weights and (any(w < 0 for w in self.portfolio_weights) or not math.isclose(sum(self.portfolio_weights), 1)):
            raise ValueError('Long-only portfolio weights must sum to 1')
        if self.portfolio_holdings:
            if len({h.symbol for h in self.portfolio_holdings})!=len(self.portfolio_holdings): raise ValueError('Duplicate portfolio symbols')
            weights=[h.weight for h in self.portfolio_holdings]
            if not math.isclose(sum(weights),1,abs_tol=1e-8): raise ValueError('Constituent weights must sum to 1')
            if self.portfolio_weights and (len(weights)!=len(self.portfolio_weights) or any(not math.isclose(a,b,abs_tol=1e-8) for a,b in zip(weights,self.portfolio_weights))):
                raise ValueError('Legacy and constituent weights disagree')
            if sum(len(h.prices) for h in self.portfolio_holdings)>50000: raise ValueError('At most 50000 constituent prices are supported')
        sources=[h.provenance for h in self.portfolio_holdings]+([self.debt_schedule.provenance] if self.debt_schedule else [])
        if self.risk_score_history:
            history=self.risk_score_history;sources.append(history.provenance)
            if history.entity_name.casefold()!=self.entity_name.casefold() or history.holding_days!=self.config.holding_days or not math.isclose(history.confidence,self.config.confidence):
                raise ValueError('Risk score history must match the entity, model horizon and confidence configuration')
            evidence_dates=[s.period for s in self.statements]+[p.date for p in self.prices]+[p.date for h in self.portfolio_holdings for p in h.prices]
            if evidence_dates and history.observations[-1].date>max(evidence_dates):
                raise ValueError('Risk score history must not extend beyond the assessment evidence period')
        if any(p.currency!=self.provenance.currency or p.synthetic!=self.provenance.synthetic for p in sources):
            raise ValueError('Constituents and debt schedule must share the assessment currency and synthetic/real origin')
        if self.debt_schedule and self.statements:
            s=self.statements[-1];schedule=self.debt_schedule
            if schedule.as_of!=s.period: raise ValueError('Debt as_of must match the latest statement period')
            principal=sum(p.principal for p in schedule.payments)
            if s.total_debt is not None:
                if principal>s.total_debt+max(.01,s.total_debt*1e-6): raise ValueError('Scheduled principal exceeds total debt')
                if schedule.complete and not math.isclose(principal,s.total_debt,rel_tol=1e-6,abs_tol=.01): raise ValueError('Complete schedule must reconcile to total debt')
        if not self.statements and not self.prices and not self.operational and not self.portfolio_holdings and not self.debt_schedule:
            raise ValueError('At least one evidence source is required')
        return self


class Metric(StrictModel):
    value: float | None
    formula: str
    unit: str = 'ratio'
    assumptions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    limitation: str | None = None


class Finding(StrictModel):
    id: str
    agent_id: str
    dimension: str
    claim: str
    evidence: list[str]
    metric_refs: list[str]
    monitoring_action: str
    assumptions: list[str] = Field(default_factory=list)


class SpecialistInsight(StrictModel):
    kind: Literal['risk_driver', 'monitoring', 'limitation']
    text: str = Field(min_length=1, max_length=1200)
    finding_ids: list[str] = Field(max_length=20)
    metric_refs: list[str] = Field(max_length=20)
    evidence_refs: list[str] = Field(min_length=1, max_length=30)


class SpecialistAnalysis(StrictModel):
    """LLMs interpret supplied evidence; they have no score or metric write fields."""
    dimension: Literal['financial', 'credit', 'market', 'liquidity', 'operational']
    insights: list[SpecialistInsight] = Field(min_length=1, max_length=10)
    limitations: list[str] = Field(min_length=1, max_length=10)


class LLMInterpretation(StrictModel):
    status: Literal['completed', 'failed', 'not_requested']
    analysis: SpecialistAnalysis | None = None
    provider: str
    model: str | None = None
    prompt_sha256: str | None = None
    validation: str = 'Structural and reference checks only; semantic conclusions are unverified'
    error: str | None = None
    usage: dict = Field(default_factory=dict)


class ScoreComponent(StrictModel):
    id: str
    metric_refs: list[str]
    input_fields: list[str]
    evidence: list[str]
    score: float = Field(ge=0,le=100)
    within_dimension_weight: float = Field(ge=0,le=1)
    included: bool


class AgentOutput(StrictModel):
    agent_id: str
    dimension: str
    status: Literal['completed', 'incomplete', 'failed']
    score: float | None = Field(None, ge=0, le=100)
    confidence: Literal['high', 'moderate', 'low', 'unavailable']
    metrics: dict[str, Metric] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    summary: str
    duration_seconds: float = 0
    llm_interpretation: LLMInterpretation | None = None
    analytics: dict = Field(default_factory=dict)
    score_components: list[ScoreComponent] = Field(default_factory=list)


class Issue(StrictModel):
    id: str
    agent_id: str
    severity: Literal['error', 'warning']
    rule: str
    evidence: list[str]
    correction: str
    correctable: bool
