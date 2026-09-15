"""catalogs

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-15

IT directions, IT products, university contacts and managers, licence contracts, and new university
fields (decisions D-136–D-141, docs/design/catalogs.md). New university columns have server defaults,
so existing rows are filled without a data migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'it_directions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('it_directions_pkey')),
        sa.UniqueConstraint('name', name=op.f('it_directions_name_key')),
    )
    op.create_table(
        'it_products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor', sa.String(length=200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('name', sa.String(length=200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('it_products_pkey')),
        sa.UniqueConstraint('vendor', 'name', name=op.f('it_products_vendor_key')),
    )
    op.create_table(
        'contracts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_number', sa.String(length=100), nullable=False),
        sa.Column('university_id', sa.Integer(), nullable=False),
        sa.Column('it_product_id', sa.Integer(), nullable=False),
        sa.Column('signed_at', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=False),
        sa.Column('transfer_status', sa.String(length=20), server_default='not_started', nullable=False),
        sa.Column('manager_user_id', sa.Integer(), nullable=True),
        sa.Column('manager_name', sa.String(length=200, collation='ru-RU-x-icu'), server_default='', nullable=False),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("transfer_status in ('not_started', 'in_progress', 'transferred', 'cancelled')", name=op.f('contracts_transfer_status_check')),
        sa.CheckConstraint('valid_until >= signed_at', name=op.f('contracts_valid_period_check')),
        sa.ForeignKeyConstraint(['it_product_id'], ['it_products.id'], name=op.f('contracts_it_product_id_fkey')),
        sa.ForeignKeyConstraint(['manager_user_id'], ['users.id'], name=op.f('contracts_manager_user_id_fkey')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('contracts_university_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('contracts_pkey')),
        sa.UniqueConstraint('contract_number', name=op.f('contracts_contract_number_key')),
    )
    op.create_index(op.f('ix_contracts_it_product_id'), 'contracts', ['it_product_id'], unique=False)
    op.create_index(op.f('ix_contracts_manager_user_id'), 'contracts', ['manager_user_id'], unique=False)
    op.create_index(op.f('ix_contracts_university_id'), 'contracts', ['university_id'], unique=False)
    op.create_table(
        'it_product_directions',
        sa.Column('it_product_id', sa.Integer(), nullable=False),
        sa.Column('it_direction_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['it_direction_id'], ['it_directions.id'], name=op.f('it_product_directions_it_direction_id_fkey')),
        sa.ForeignKeyConstraint(['it_product_id'], ['it_products.id'], name=op.f('it_product_directions_it_product_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('it_product_id', 'it_direction_id', name=op.f('it_product_directions_pkey')),
    )
    op.create_table(
        'university_contacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('university_id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(length=200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('position', sa.String(length=200, collation='ru-RU-x-icu'), server_default='', nullable=False),
        sa.Column('email', sa.String(length=254), server_default='', nullable=False),
        sa.Column('phone', sa.String(length=50), server_default='', nullable=False),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('university_contacts_university_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('university_contacts_pkey')),
        sa.UniqueConstraint('university_id', 'full_name', name=op.f('university_contacts_university_id_key')),
    )
    op.create_index(op.f('ix_university_contacts_university_id'), 'university_contacts', ['university_id'], unique=False)
    op.create_table(
        'university_managers',
        sa.Column('university_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('assigned_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by_user_id'], ['users.id'], name=op.f('university_managers_assigned_by_user_id_fkey')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('university_managers_university_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('university_managers_user_id_fkey')),
        sa.PrimaryKeyConstraint('university_id', 'user_id', name=op.f('university_managers_pkey')),
    )
    op.create_index(op.f('ix_university_managers_user_id'), 'university_managers', ['user_id'], unique=False)
    op.create_table(
        'contract_contacts',
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('university_contact_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], name=op.f('contract_contacts_contract_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['university_contact_id'], ['university_contacts.id'], name=op.f('contract_contacts_university_contact_id_fkey')),
        sa.PrimaryKeyConstraint('contract_id', 'university_contact_id', name=op.f('contract_contacts_pkey')),
    )
    op.add_column('universities', sa.Column('short_name', sa.String(length=100, collation='ru-RU-x-icu'), server_default='', nullable=False))
    op.add_column('universities', sa.Column('region', sa.String(length=100, collation='ru-RU-x-icu'), server_default='', nullable=False))
    op.add_column('universities', sa.Column('website', sa.String(length=300), server_default='', nullable=False))
    op.add_column('universities', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.create_unique_constraint(op.f('universities_name_key'), 'universities', ['name'])


def downgrade() -> None:
    op.drop_constraint(op.f('universities_name_key'), 'universities', type_='unique')
    op.drop_column('universities', 'is_active')
    op.drop_column('universities', 'website')
    op.drop_column('universities', 'region')
    op.drop_column('universities', 'short_name')
    op.drop_table('contract_contacts')
    op.drop_index(op.f('ix_university_managers_user_id'), table_name='university_managers')
    op.drop_table('university_managers')
    op.drop_index(op.f('ix_university_contacts_university_id'), table_name='university_contacts')
    op.drop_table('university_contacts')
    op.drop_table('it_product_directions')
    op.drop_index(op.f('ix_contracts_university_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_manager_user_id'), table_name='contracts')
    op.drop_index(op.f('ix_contracts_it_product_id'), table_name='contracts')
    op.drop_table('contracts')
    op.drop_table('it_products')
    op.drop_table('it_directions')
