import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_empty_compose_values_use_defaults_and_model_overrides_are_bounded(monkeypatch):
    monkeypatch.setenv('SPECIALIST_MODELS','')
    monkeypatch.setenv('SPECIALIST_MODEL','')
    cfg=Settings(_env_file=None)
    assert cfg.specialist_models=={} and cfg.specialist_model is None
    cfg=Settings(_env_file=None,specialist_models={'credit':'credit-specific'},specialist_model='shared-model')
    assert cfg.model_for_specialist('credit')=='credit-specific'
    assert cfg.model_for_specialist('market')=='shared-model'
    with pytest.raises(ValidationError):Settings(_env_file=None,specialist_models={'unknown':'model'})
