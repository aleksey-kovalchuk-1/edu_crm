"""bind login to browser

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15

Adds the hash of the per-browser login cookie to pending logins (login CSRF protection, decision D-134).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pending logins started before browser binding cannot be completed safely; they expire within ten minutes anyway.
    op.execute('delete from login_states')
    op.add_column('login_states', sa.Column('browser_hash', sa.String(length=64), nullable=False))


def downgrade() -> None:
    op.drop_column('login_states', 'browser_hash')
