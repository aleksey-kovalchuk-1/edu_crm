"""catalog imports

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-15 15:37:14.719397
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('catalog_imports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('header_row', sa.Integer(), nullable=False),
    sa.Column('headers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('suggested_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status in ('uploaded', 'applied')", name=op.f('catalog_imports_status_check')),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('catalog_imports_created_by_user_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('catalog_imports_pkey'))
    )
    op.create_index(op.f('ix_catalog_imports_created_at'), 'catalog_imports', ['created_at'], unique=False)
    op.create_index(op.f('ix_catalog_imports_created_by_user_id'), 'catalog_imports', ['created_by_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_catalog_imports_created_by_user_id'), table_name='catalog_imports')
    op.drop_index(op.f('ix_catalog_imports_created_at'), table_name='catalog_imports')
    op.drop_table('catalog_imports')
