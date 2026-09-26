"""Keyed document equality fingerprints.

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'learner_fingerprints',
        sa.Column('learner_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('key_version', sa.Integer(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.CheckConstraint("kind in ('snils', 'passport_pair')", name=op.f('learner_fingerprints_kind_check')),
        sa.ForeignKeyConstraint(['learner_id'], ['learners.id'], name=op.f('learner_fingerprints_learner_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('learner_id', 'kind', 'key_version', name=op.f('learner_fingerprints_pkey')),
    )
    op.create_index('ix_learner_fingerprints_lookup', 'learner_fingerprints', ['kind', 'key_version', 'digest'])


def downgrade() -> None:
    op.drop_index('ix_learner_fingerprints_lookup', table_name='learner_fingerprints')
    op.drop_table('learner_fingerprints')
