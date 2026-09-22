"""email sender identities

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RU = 'ru-RU-x-icu'


def upgrade() -> None:
    op.create_table(
        'email_sender_identities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_address', sa.String(length=254), nullable=False),
        sa.Column('display_name', sa.String(length=200, collation=RU), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('email_sender_identities_pkey')),
        sa.UniqueConstraint('email_address', name=op.f('email_sender_identities_email_address_key')),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('email_sender_identities_created_by_user_id_fkey')),
    )
    op.add_column('users', sa.Column('email_sender_identity_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('users_email_sender_identity_id_fkey'), 'users', 'email_sender_identities',
        ['email_sender_identity_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(op.f('users_email_sender_identity_id_fkey'), 'users', type_='foreignkey')
    op.drop_column('users', 'email_sender_identity_id')
    op.drop_table('email_sender_identities')
