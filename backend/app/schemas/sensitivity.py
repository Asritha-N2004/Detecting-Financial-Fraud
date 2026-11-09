from pydantic import field_validator
from app.schemas.domain import StrictModel,SensitivityConfig
from app.financial_engine.sensitivity import validate_weights


class SensitivityRequest(SensitivityConfig):
    weights: dict[str,float] | None = None

    @field_validator('weights')
    @classmethod
    def valid_weights(cls,value):
        if value is not None:validate_weights(value)
        return value
