"""integration links

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-17

Idempotency key for mock LMS/CMS inbound deliveries (T-060, D-184-D-187): `(source, external_id)`
identifies which `Launch` a repeated delivery updates instead of duplicating.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONNECTOR_SOURCES = ('lms', 'cms')


def upgrade() -> None:
    op.create_table(
        'integration_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=200), nullable=False),
        sa.Column('launch_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f"source in ({', '.join(repr(s) for s in CONNECTOR_SOURCES)})", name=op.f('integration_links_source_check')),
        sa.ForeignKeyConstraint(['launch_id'], ['launches.id'], name=op.f('integration_links_launch_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('integration_links_pkey')),
        sa.UniqueConstraint('source', 'external_id', name=op.f('integration_links_source_key')),
    )
    op.create_index(op.f('ix_integration_links_launch_id'), 'integration_links', ['launch_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_integration_links_launch_id'), table_name='integration_links')
    op.drop_table('integration_links')
