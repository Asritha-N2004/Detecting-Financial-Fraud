from typing import Literal
from pydantic import Field
from app.schemas.domain import StrictModel


class ScenarioAssumptions(StrictModel):
    market_return: float = Field(0,ge=-1,le=1)
    rate_increase: float = Field(0,ge=0,le=.5)
    revenue_change: float = Field(0,ge=-1,le=1)
    cost_change: float = Field(0,ge=-1,le=2)
    cash_change: float = Field(0,ge=-1,le=0)
    variable_cost_share: float = Field(.6,ge=0,le=1)
    tax_rate: float = Field(.25,ge=0,le=1)
    capex: float = Field(0,ge=0)
    dividends: float = Field(0,ge=0)
    collection_delay_days: int = Field(0,ge=0,le=180)
    horizon_days: Literal[365] = 365
    asset_shocks: dict[str,float] = Field(default_factory=dict)


class StressRequest(StrictModel):
    scenario: str = 'combined_adverse'
    market_return: float | None = Field(None,ge=-1,le=1)
    rate_increase: float | None = Field(None,ge=0,le=.5)
    revenue_change: float | None = Field(None,ge=-1,le=1)
    cost_change: float | None = Field(None,ge=-1,le=2)
    cash_change: float | None = Field(None,ge=-1,le=0)
    variable_cost_share: float | None = Field(None,ge=0,le=1)
    tax_rate: float | None = Field(None,ge=0,le=1)
    capex: float | None = Field(None,ge=0)
    dividends: float | None = Field(None,ge=0)
    collection_delay_days: int | None = Field(None,ge=0,le=180)
    horizon_days: Literal[365] | None = None
    asset_shocks: dict[str,float] | None = None
