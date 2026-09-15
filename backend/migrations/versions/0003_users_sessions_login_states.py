"""users sessions login states

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-15

Local mirror of Keycloak users, server-side browser sessions, and pending logins.
See docs/design/authentication.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_states',
        sa.Column('state_hash', sa.String(length=64), nullable=False),
        sa.Column('nonce', sa.String(length=64), nullable=False),
        sa.Column('code_verifier', sa.String(length=128), nullable=False),
        sa.Column('next_path', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('state_hash', name=op.f('login_states_pkey')),
    )
    op.create_index(op.f('ix_login_states_expires_at'), 'login_states', ['expires_at'], unique=False)
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('keycloak_sub', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('full_name', sa.String(length=200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('roles', postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('users_pkey')),
        sa.UniqueConstraint('keycloak_sub', name=op.f('users_keycloak_sub_key')),
    )
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('csrf_token', sa.String(length=64), nullable=False),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('sessions_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('sessions_pkey')),
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('users')
    op.drop_index(op.f('ix_login_states_expires_at'), table_name='login_states')
    op.drop_table('login_states')
