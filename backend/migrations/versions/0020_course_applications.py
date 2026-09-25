"""Course applications without inferred payment status.

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'course_applications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('external_number', sa.String(100), nullable=False),
        sa.Column('learner_id', sa.Integer(), nullable=False),
        sa.Column('course', sa.String(200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('stream_number', sa.String(100), nullable=False),
        sa.Column('payment_status', sa.String(40), server_default='unconfirmed_by_data', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("payment_status = 'unconfirmed_by_data'", name=op.f('course_applications_payment_status_check')),
        sa.ForeignKeyConstraint(['learner_id'], ['learners.id'], name=op.f('course_applications_learner_id_fkey')),
        sa.UniqueConstraint('external_number', name=op.f('course_applications_external_number_key')),
    )
    op.create_index(op.f('ix_course_applications_learner_id'), 'course_applications', ['learner_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_course_applications_learner_id'), table_name='course_applications')
    op.drop_table('course_applications')
