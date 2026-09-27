"""In-app notifications, per-user preferences and pause.

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('body', sa.String(500), nullable=False, server_default=''),
        sa.Column('link_type', sa.String(20), nullable=False),
        sa.Column('link_id', sa.Integer(), nullable=False),
        sa.Column('university_id', sa.Integer(), nullable=True),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('dedupe_key', sa.String(120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('notifications_user_id_fkey')),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('notifications_actor_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('notifications_pkey')),
    )
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'])
    op.create_index('ix_notifications_user_dedupe', 'notifications', ['user_id', 'dedupe_key'], unique=True,
                    postgresql_where=sa.text('dedupe_key IS NOT NULL'))
    op.create_table(
        'notification_preferences',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('notification_preferences_user_id_fkey')),
        sa.PrimaryKeyConstraint('user_id', 'event_type', name=op.f('notification_preferences_pkey')),
    )
    op.add_column('users', sa.Column('notifications_paused_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'notifications_paused_until')
    op.drop_table('notification_preferences')
    op.drop_index('ix_notifications_user_dedupe', 'notifications')
    op.drop_index('ix_notifications_user_created', 'notifications')
    op.drop_table('notifications')
