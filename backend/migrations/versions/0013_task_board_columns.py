"""task board columns

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-22

Adds the custom-column fields for the Deadlines board (rebuilt as a Kanban board, docs/design/tasks.md)
and its equivalent addition to the personal planner: `planner_custom_columns`, `planner_custom_members`,
`deadline_columns`, `deadline_positions`, `deadline_custom_columns`, `deadline_custom_members` — all
JSONB, nullable. Additive and backward compatible: existing rows get NULL on the new columns, read as
"no custom columns / default system order yet" by the API. `planner_columns`/`planner_positions` are
unchanged in shape (still list/dict respectively) — only their *meaning* widens to also carry
`custom:<id>` refs alongside status codes, entirely at the application layer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = (
    'planner_custom_columns',
    'planner_custom_members',
    'deadline_columns',
    'deadline_positions',
    'deadline_custom_columns',
    'deadline_custom_members',
)


def upgrade() -> None:
    for name in NEW_COLUMNS:
        op.add_column('task_user_preferences', sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    for name in reversed(NEW_COLUMNS):
        op.drop_column('task_user_preferences', name)
