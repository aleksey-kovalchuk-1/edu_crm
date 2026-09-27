"""Remember each CRM session's Keycloak session id, so ending a session can also end it in Keycloak.

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('keycloak_session_id', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('sessions', 'keycloak_session_id')
