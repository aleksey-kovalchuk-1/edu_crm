"""Protected learner profiles with optional fields.

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    ru = lambda length: sa.String(length, collation='ru-RU-x-icu')
    op.create_table(
        'learners',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('last_name', ru(200), nullable=False),
        sa.Column('first_name', ru(200), nullable=False),
        sa.Column('middle_name', ru(200), server_default='', nullable=False),
        sa.Column('phone', sa.String(50), server_default='', nullable=False),
        sa.Column('email', sa.String(254), server_default='', nullable=False),
        sa.Column('snils_encrypted', sa.Text(), nullable=True),
        sa.Column('passport_series_encrypted', sa.Text(), nullable=True),
        sa.Column('passport_number_encrypted', sa.Text(), nullable=True),
        sa.Column('passport_issued_by_encrypted', sa.Text(), nullable=True),
        sa.Column('passport_issued_at', sa.Date(), nullable=True),
        sa.Column('passport_department_code_encrypted', sa.Text(), nullable=True),
        sa.Column('gender', sa.String(20), nullable=True),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('registration_region', ru(200), nullable=True),
        sa.Column('registration_locality', ru(200), nullable=True),
        sa.Column('registration_street', ru(200), nullable=True),
        sa.Column('registration_house', sa.String(50), nullable=True),
        sa.Column('registration_apartment', sa.String(50), nullable=True),
        sa.Column('postal_code', sa.String(20), nullable=True),
        sa.Column('dative_first_name', ru(200), nullable=True),
        sa.Column('dative_last_name', ru(200), nullable=True),
        sa.Column('dative_middle_name', ru(200), nullable=True),
        sa.Column('education', ru(200), nullable=True),
        sa.Column('diploma_profession', ru(200), nullable=True),
        sa.Column('diploma_institution', ru(200), nullable=True),
        sa.Column('diploma_last_name', ru(200), nullable=True),
        sa.Column('diploma_number_encrypted', sa.Text(), nullable=True),
        sa.Column('diploma_series_encrypted', sa.Text(), nullable=True),
        sa.Column('diploma_registration_number_encrypted', sa.Text(), nullable=True),
        sa.Column('diploma_issued_at', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_learners_phone'), 'learners', ['phone'])
    op.create_index(op.f('ix_learners_email'), 'learners', ['email'])


def downgrade() -> None:
    op.drop_index(op.f('ix_learners_email'), table_name='learners')
    op.drop_index(op.f('ix_learners_phone'), table_name='learners')
    op.drop_table('learners')
