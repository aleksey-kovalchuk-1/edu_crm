"""phone verification

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-16

CRM-owned phone verification (not a Keycloak/OIDC change, D-002 stays intact: Keycloak remains the sole
identity provider). `users.phone`/`phone_verified_at` record a verified number; `phone_verification_codes`
holds short-lived, hashed one-time codes with attempt limiting.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(length=20), server_default='', nullable=False))
    op.add_column('users', sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'phone_verification_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        # The number this code verifies; kept alongside the code so a later change to users.phone before
        # verification completes can't be confused with what the code was actually sent to.
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('correlation_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('phone_verification_codes_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('phone_verification_codes_pkey')),
    )
    op.create_index(op.f('ix_phone_verification_codes_user_id'), 'phone_verification_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_phone_verification_codes_created_at'), 'phone_verification_codes', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_phone_verification_codes_created_at'), table_name='phone_verification_codes')
    op.drop_index(op.f('ix_phone_verification_codes_user_id'), table_name='phone_verification_codes')
    op.drop_table('phone_verification_codes')
    op.drop_column('users', 'phone_verified_at')
    op.drop_column('users', 'phone')
