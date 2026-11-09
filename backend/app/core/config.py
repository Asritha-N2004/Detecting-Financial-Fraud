from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', env_ignore_empty=True)
    database_url: str = 'sqlite:///./risk.db'
    database_url_unpooled: str = ''
    database_schema: str = Field('',pattern=r'^(?:[a-z][a-z0-9_]{0,62})?$')
    deploy_migrations: bool = False
    jwt_secret: str = ''
    token_minutes: int = Field(60,ge=1,le=1440)
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'
    model_provider: str = 'deterministic'
    specialist_provider: Literal['deterministic', 'openai-compatible'] = 'deterministic'
    specialist_model: str | None = None
    specialist_models: dict[str,str] = Field(default_factory=dict)
    agent_prompts_dir: str | None = None
    llm_max_tool_rounds: int = Field(3, ge=1, le=5)
    llm_max_completion_tokens: int = Field(2000, ge=100, le=8000)
    worker_enabled: bool = True
    request_worker_enabled: bool = False
    request_worker_seconds: int = Field(20, ge=1, le=240)
    worker_poll_seconds: float = Field(.5, ge=.02, le=30)
    job_lease_seconds: int = Field(60, ge=10, le=3600)
    job_max_attempts: int = Field(3, ge=1, le=10)
    job_retry_seconds: float = Field(2, ge=0, le=300)
    openai_api_key: str = ''
    openai_model: str = 'gpt-4.1-mini'
    openai_base_url: str | None = None
    agent_timeout_seconds: float = Field(30,gt=0,le=300)
    agent_retries: int = Field(1,ge=0,le=3)
    upload_limit_bytes: int = Field(2_000_000,ge=1000,le=20_000_000)

    @field_validator('database_url', 'database_url_unpooled')
    @classmethod
    def normalize_postgres_url(cls, value):
        # Marketplace URLs use the generic scheme; explicitly select psycopg 3.
        for prefix in ('postgres://', 'postgresql://'):
            if value.startswith(prefix):
                return 'postgresql+psycopg://' + value[len(prefix):]
        return value

    @field_validator('specialist_models')
    @classmethod
    def valid_specialist_models(cls, value):
        if not set(value).issubset({'financial','credit','market','liquidity','operational'}) or any(not name.strip() or len(name)>150 for name in value.values()):
            raise ValueError('Specialist model overrides require known dimensions and nonempty model IDs')
        return value

    def model_for_specialist(self, dimension: str) -> str:
        return self.specialist_models.get(dimension,self.specialist_model or self.openai_model)


@lru_cache
def settings() -> Settings:
    return Settings()
