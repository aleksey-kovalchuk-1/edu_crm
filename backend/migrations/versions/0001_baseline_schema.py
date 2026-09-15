"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-09-15

Reproduces the schema that the application built with create_all before migrations existed.
Existing databases of that shape are stamped with this revision instead of being recreated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'annual_metrics',
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('applications', sa.Integer(), nullable=False),
        sa.Column('students', sa.Integer(), nullable=False),
        sa.Column('streams', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('year', name=op.f('annual_metrics_pkey')),
    )
    op.create_table(
        'universities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('contact', sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('universities_pkey')),
    )
    op.create_table(
        'launches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('university_id', sa.Integer(), nullable=False),
        sa.Column('program', sa.String(length=200), nullable=False),
        sa.Column('product', sa.String(length=200), nullable=False),
        sa.Column('owner', sa.String(length=100), nullable=False),
        sa.Column('students', sa.Integer(), nullable=False),
        sa.Column('stage', sa.Integer(), nullable=False),
        sa.Column('deadline', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('launches_university_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('launches_pkey')),
    )
    op.create_table(
        'stage_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('launch_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['launch_id'], ['launches.id'], name=op.f('stage_events_launch_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('stage_events_pkey')),
    )
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('launch_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('owner', sa.String(length=100), nullable=False),
        sa.Column('deadline', sa.Date(), nullable=False),
        sa.Column('done', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['launch_id'], ['launches.id'], name=op.f('tasks_launch_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('tasks_pkey')),
    )


def downgrade() -> None:
    op.drop_table('tasks')
    op.drop_table('stage_events')
    op.drop_table('launches')
    op.drop_table('universities')
    op.drop_table('annual_metrics')
