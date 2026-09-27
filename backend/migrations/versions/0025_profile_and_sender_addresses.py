"""Editable profile fields, rename-safe interaction owners, and approved sender addresses.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None

RU = 'ru-RU-x-icu'
SENDERS = 'email_sender_identities'


def upgrade() -> None:
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=False, server_default=''))
    op.add_column('users', sa.Column('middle_name', sa.String(100), nullable=False, server_default=''))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=False, server_default=''))
    op.add_column('users', sa.Column('timezone', sa.String(64), nullable=False, server_default='Europe/Moscow'))
    op.add_column('users', sa.Column('telegram', sa.String(32), nullable=False, server_default=''))
    op.add_column('users', sa.Column('whatsapp', sa.String(16), nullable=False, server_default=''))

    op.alter_column('launches', 'owner', type_=sa.String(200, collation=RU), existing_type=sa.String(100, collation=RU),
                    existing_nullable=False)
    op.add_column('launches', sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_launches_owner_user_id', 'launches', ['owner_user_id'])
    # Link only when exactly one ACTIVE user has the same normalized name; never rewrite the text.
    op.execute(r"""
        UPDATE launches l SET owner_user_id = m.user_id
        FROM (
            SELECT l2.id AS launch_id, min(u.id) AS user_id
            FROM launches l2 JOIN users u
              ON u.is_active
             AND lower(regexp_replace(btrim(u.full_name), '\s+', ' ', 'g'))
               = lower(regexp_replace(btrim(l2.owner), '\s+', ' ', 'g'))
            GROUP BY l2.id HAVING count(*) = 1
        ) m
        WHERE l.id = m.launch_id
    """)

    op.add_column(SENDERS, sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column(SENDERS, sa.Column('status', sa.String(32), nullable=False, server_default='active'))
    op.create_check_constraint(
        op.f('email_sender_identities_status_check'), SENDERS,
        "status in ('pending_approval', 'awaiting_confirmation', 'active', 'rejected')",
    )
    op.add_column(SENDERS, sa.Column('requested_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column(SENDERS, sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(SENDERS, sa.Column('approved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column(SENDERS, sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(SENDERS, sa.Column('rejection_reason', sa.String(500), nullable=False, server_default=''))
    op.add_column(SENDERS, sa.Column('confirmation_token_hash', sa.String(64), nullable=True))
    op.add_column(SENDERS, sa.Column('confirmation_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(SENDERS, sa.Column('confirmation_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(SENDERS, sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_email_sender_identities_owner_user_id', SENDERS, ['owner_user_id'])
    op.create_unique_constraint(op.f('email_sender_identities_confirmation_token_hash_key'), SENDERS, ['confirmation_token_hash'])


def downgrade() -> None:
    op.drop_constraint(op.f('email_sender_identities_confirmation_token_hash_key'), SENDERS, type_='unique')
    op.drop_index('ix_email_sender_identities_owner_user_id', SENDERS)
    for name in ('confirmed_at', 'confirmation_sent_at', 'confirmation_expires_at', 'confirmation_token_hash',
                 'rejection_reason', 'approved_at', 'approved_by_user_id', 'requested_at', 'requested_by_user_id'):
        op.drop_column(SENDERS, name)
    op.drop_constraint(op.f('email_sender_identities_status_check'), SENDERS, type_='check')
    op.drop_column(SENDERS, 'status')
    op.drop_column(SENDERS, 'owner_user_id')
    op.drop_index('ix_launches_owner_user_id', 'launches')
    op.drop_column('launches', 'owner_user_id')
    op.execute('UPDATE launches SET owner = left(owner, 100)')
    op.alter_column('launches', 'owner', type_=sa.String(100, collation=RU), existing_type=sa.String(200, collation=RU),
                    existing_nullable=False)
    for name in ('whatsapp', 'telegram', 'timezone', 'last_name', 'middle_name', 'first_name'):
        op.drop_column('users', name)
