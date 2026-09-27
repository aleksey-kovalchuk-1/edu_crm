"""Share selected universities with all managers without broadening task permissions.

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('universities', sa.Column(
        'team_visible_to_managers', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade() -> None:
    op.drop_column('universities', 'team_visible_to_managers')
