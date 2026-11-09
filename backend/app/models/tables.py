"""Tenant-scoped durable inputs, analysis artifacts, and audit records."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, ForeignKey, JSON, DateTime, Float, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default='analyst')


class Entity(Base):
    __tablename__ = 'financial_entities'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3))


class Assessment(Base):
    __tablename__ = 'risk_assessments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey('financial_entities.id'), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    assessment_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40), default='pending', index=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), default='rules-2.0')
    input_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ArtifactMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    assessment_id: Mapped[str] = mapped_column(ForeignKey('risk_assessments.id', ondelete='CASCADE'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Execution(ArtifactMixin, Base):
    __tablename__ = 'agent_executions'
    agent_name: Mapped[str] = mapped_column(String(60))
    execution_status: Mapped[str] = mapped_column(String(30))
    execution_time: Mapped[float] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Finding(ArtifactMixin, Base):
    __tablename__ = 'agent_findings'


class Reflection(ArtifactMixin, Base):
    __tablename__ = 'reflection_iterations'
    __table_args__ = (UniqueConstraint('assessment_id', 'iteration_number'),)
    iteration_number: Mapped[int] = mapped_column(Integer)


class CriticReport(ArtifactMixin, Base):
    __tablename__ = 'critic_reports'


class Score(ArtifactMixin, Base):
    __tablename__ = 'risk_scores'


class Explanation(ArtifactMixin, Base):
    __tablename__ = 'explanations'


class StressResult(ArtifactMixin, Base):
    __tablename__ = 'stress_test_results'


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class InputMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    entity_id: Mapped[str] = mapped_column(ForeignKey('financial_entities.id'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinancialStatement(InputMixin, Base):
    __tablename__ = 'financial_statements'


class MarketData(InputMixin, Base):
    __tablename__ = 'market_data'


class Portfolio(InputMixin, Base):
    __tablename__ = 'portfolios'


class Asset(Base):
    __tablename__ = 'assets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id'), index=True)
    symbol: Mapped[str] = mapped_column(String(40))
    weight: Mapped[float] = mapped_column(Float)


class AssessmentJob(Base):
    """One durable queue entry per assessment; lease_token fences stale workers."""
    __tablename__ = 'assessment_jobs'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    assessment_id: Mapped[str] = mapped_column(ForeignKey('risk_assessments.id',ondelete='CASCADE'),unique=True)
    status: Mapped[str] = mapped_column(String(20),index=True,default='queued')
    attempts: Mapped[int] = mapped_column(Integer,default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),index=True,default=now)
    lease_token: Mapped[str | None] = mapped_column(String(36),nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True,index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    checkpoint_json: Mapped[dict | None] = mapped_column(JSON,nullable=True)
    runtime_json: Mapped[dict] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(String(100),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
