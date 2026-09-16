"""ingestion foundation: correlation ids, background jobs, saved mappings

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-16

Shared foundation for file ingestion (docs/design/file-ingestion-plan.md, D-165-D-170): a correlation id on
audit events, a PostgreSQL-backed job queue (no Redis, D-166), and saved column-mapping profiles for the
generic entity-import wizard (T-091). No existing tables lose columns; this migration only adds.

Renumbered during integration (`ai/integration-candidate`, D-164/D-174): this migration and 0011_documents
were originally 0009/0010 on `ai/file-ingestion`, colliding with `ai/phone-verification`'s own 0009. Shifted
by one so phone verification keeps its original revision id and the three branches form one linear chain
(0008 -> 0009 phone verification -> 0010 ingestion foundation -> 0011 documents).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_STATUSES = ('queued', 'running', 'succeeded', 'failed')


def upgrade() -> None:
    op.add_column('audit_events', sa.Column('correlation_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_audit_events_correlation_id'), 'audit_events', ['correlation_id'], unique=False)

    op.create_table(
        'background_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('correlation_id', sa.String(length=36), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status in ({', '.join(repr(s) for s in JOB_STATUSES)})", name=op.f('background_jobs_status_check')),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('background_jobs_created_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('background_jobs_pkey')),
    )
    op.create_index('ix_background_jobs_status_id', 'background_jobs', ['status', 'id'], unique=False)
    op.create_index(op.f('ix_background_jobs_correlation_id'), 'background_jobs', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_background_jobs_created_at'), 'background_jobs', ['created_at'], unique=False)

    op.create_table(
        'import_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=120, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('import_mappings_created_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('import_mappings_pkey')),
        sa.UniqueConstraint('entity', 'name', name=op.f('import_mappings_entity_key')),
    )
    op.create_index(op.f('ix_import_mappings_entity'), 'import_mappings', ['entity'], unique=False)


def downgrade() -> None:
    op.drop_table('import_mappings')
    op.drop_index('ix_background_jobs_created_at', table_name='background_jobs')
    op.drop_index('ix_background_jobs_correlation_id', table_name='background_jobs')
    op.drop_index('ix_background_jobs_status_id', table_name='background_jobs')
    op.drop_table('background_jobs')
    op.drop_index(op.f('ix_audit_events_correlation_id'), table_name='audit_events')
    op.drop_column('audit_events', 'correlation_id')
