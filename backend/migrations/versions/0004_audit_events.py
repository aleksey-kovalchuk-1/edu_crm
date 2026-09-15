"""audit events

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-15

Append-only audit trail of user actions (decisions D-105, D-131).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=True),
        sa.Column('entity_id', sa.String(length=64), nullable=True),
        sa.Column('summary', sa.String(length=300, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('audit_events_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('audit_events_pkey')),
    )
    op.create_index('ix_audit_events_entity', 'audit_events', ['entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_audit_events_occurred_at'), 'audit_events', ['occurred_at'], unique=False)
    op.create_index(op.f('ix_audit_events_user_id'), 'audit_events', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_events_user_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_occurred_at'), table_name='audit_events')
    op.drop_index('ix_audit_events_entity', table_name='audit_events')
    op.drop_table('audit_events')
