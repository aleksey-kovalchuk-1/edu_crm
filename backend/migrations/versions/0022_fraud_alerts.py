"""Human-review fraud alerts with safe metadata only.

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fraud_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('dedupe_key', sa.String(200), nullable=False),
        sa.Column('rule_code', sa.String(60), nullable=False),
        sa.Column('rule_version', sa.Integer(), nullable=False),
        sa.Column('evidence_kind', sa.String(30)),
        sa.Column('priority', sa.String(10), nullable=False),
        sa.Column('status', sa.String(20), server_default='open', nullable=False),
        sa.Column('entity_type', sa.String(30)),
        sa.Column('entity_id', sa.Integer()),
        sa.Column('related_entity_id', sa.Integer()),
        sa.Column('batch_id', sa.Integer()),
        sa.Column('row_number', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reviewed_by_user_id', sa.Integer()),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('resolution_code', sa.String(60)),
        sa.CheckConstraint("priority in ('low', 'medium', 'high')", name=op.f('fraud_alerts_priority_check')),
        sa.CheckConstraint("status in ('open', 'in_review', 'cleared', 'confirmed')", name=op.f('fraud_alerts_status_check')),
        sa.ForeignKeyConstraint(['batch_id'], ['customer_import_batches.id'], name=op.f('fraud_alerts_batch_id_fkey')),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], name=op.f('fraud_alerts_reviewed_by_user_id_fkey')),
        sa.UniqueConstraint('dedupe_key', name=op.f('fraud_alerts_dedupe_key_key')),
    )
    op.create_index(op.f('ix_fraud_alerts_batch_id'), 'fraud_alerts', ['batch_id'])
    op.create_index('ix_fraud_alerts_queue', 'fraud_alerts', ['status', 'priority', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_fraud_alerts_queue', table_name='fraud_alerts')
    op.drop_index(op.f('ix_fraud_alerts_batch_id'), table_name='fraud_alerts')
    op.drop_table('fraud_alerts')
