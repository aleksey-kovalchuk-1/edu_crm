"""Safe customer import provenance without source cell values.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'customer_import_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('template_version', sa.String(60), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rows', sa.Integer(), nullable=False),
        sa.Column('valid', sa.Integer(), nullable=False),
        sa.Column('invalid', sa.Integer(), nullable=False),
        sa.Column('skipped', sa.Integer(), nullable=False),
        sa.Column('created', sa.Integer(), nullable=False),
        sa.Column('updated', sa.Integer(), nullable=False),
        sa.CheckConstraint("kind in ('vendors', 'learners', 'applications')", name=op.f('customer_import_batches_kind_check')),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('customer_import_batches_created_by_user_id_fkey')),
    )
    op.create_index(op.f('ix_customer_import_batches_created_at'), 'customer_import_batches', ['created_at'])
    op.create_index(op.f('ix_customer_import_batches_created_by_user_id'), 'customer_import_batches', ['created_by_user_id'])
    op.create_table(
        'customer_import_row_links',
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.CheckConstraint("entity_type in ('vendor_contact', 'learner', 'course_application')", name=op.f('customer_import_row_links_entity_type_check')),
        sa.CheckConstraint("action in ('created', 'updated')", name=op.f('customer_import_row_links_action_check')),
        sa.ForeignKeyConstraint(['batch_id'], ['customer_import_batches.id'], name=op.f('customer_import_row_links_batch_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('batch_id', 'row_number', name=op.f('customer_import_row_links_pkey')),
    )
    op.create_index(op.f('ix_customer_import_row_links_entity_id'), 'customer_import_row_links', ['entity_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_customer_import_row_links_entity_id'), table_name='customer_import_row_links')
    op.drop_table('customer_import_row_links')
    op.drop_index(op.f('ix_customer_import_batches_created_by_user_id'), table_name='customer_import_batches')
    op.drop_index(op.f('ix_customer_import_batches_created_at'), table_name='customer_import_batches')
    op.drop_table('customer_import_batches')
