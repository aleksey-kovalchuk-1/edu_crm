"""task saved filters

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21

Adds `task_user_preferences.filters` (JSONB, nullable) — saved filter sets per `{view}:{scope}`
combination for the Tasks workspace's new filter dialog (docs/design/tasks.md). Additive and
backward compatible: existing rows get NULL, read as "no saved filters yet" by the API.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('task_user_preferences', sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('task_user_preferences', 'filters')
