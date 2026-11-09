"""Durable leased assessment queue and versioned workflow checkpoints."""
from alembic import op
import sqlalchemy as sa

revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('assessment_jobs',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('assessment_id',sa.String(36),sa.ForeignKey('risk_assessments.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False),
        sa.Column('max_attempts',sa.Integer(),nullable=False),
        sa.Column('available_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('lease_token',sa.String(36),nullable=True),
        sa.Column('lease_expires_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('heartbeat_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('checkpoint_json',sa.JSON(),nullable=True),
        sa.Column('runtime_json',sa.JSON(),nullable=False),
        sa.Column('last_error',sa.String(100),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    for column in ['status','available_at','lease_expires_at']:
        op.create_index('ix_assessment_jobs_'+column,'assessment_jobs',[column])
    # Existing interrupted jobs have no usable checkpoint. Queue them for a fresh
    # run instead of changing completed or deliberately unstarted assessments.
    import uuid
    from datetime import datetime,timezone
    connection=op.get_bind()
    jobs=sa.table('assessment_jobs',*[sa.column(name,typ) for name,typ in [('id',sa.String),('assessment_id',sa.String),('status',sa.String),('attempts',sa.Integer),('max_attempts',sa.Integer),('available_at',sa.DateTime(timezone=True)),('runtime_json',sa.JSON),('created_at',sa.DateTime(timezone=True)),('updated_at',sa.DateTime(timezone=True))]])
    timestamp=datetime.now(timezone.utc)
    ids=connection.execute(sa.text("SELECT id FROM risk_assessments WHERE status IN ('running','reflecting')")).scalars()
    for assessment_id in list(ids):
        connection.execute(jobs.insert().values(id=str(uuid.uuid4()),assessment_id=assessment_id,status='queued',attempts=0,max_attempts=3,available_at=timestamp,runtime_json={'legacy_adopted':True},created_at=timestamp,updated_at=timestamp))


def downgrade():
    op.drop_table('assessment_jobs')
