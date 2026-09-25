"""Supplier companies and contacts linked to existing IT products.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'vendor_companies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.UniqueConstraint('name', name=op.f('vendor_companies_name_key')),
    )
    op.add_column('it_products', sa.Column('company_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('it_products_company_id_fkey'), 'it_products', 'vendor_companies', ['company_id'], ['id'])
    op.create_index(op.f('ix_it_products_company_id'), 'it_products', ['company_id'])
    op.create_table(
        'vendor_contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('phone', sa.String(50), server_default='', nullable=False),
        sa.Column('email', sa.String(254), server_default='', nullable=False),
        sa.Column('preferred_channels', sa.ARRAY(sa.String(50)), server_default='{}', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['vendor_companies.id'], name=op.f('vendor_contacts_company_id_fkey')),
    )
    op.create_index(op.f('ix_vendor_contacts_company_id'), 'vendor_contacts', ['company_id'])
    op.create_table(
        'vendor_contact_products',
        sa.Column('vendor_contact_id', sa.Integer(), nullable=False),
        sa.Column('it_product_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['vendor_contact_id'], ['vendor_contacts.id'], name=op.f('vendor_contact_products_vendor_contact_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['it_product_id'], ['it_products.id'], name=op.f('vendor_contact_products_it_product_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('vendor_contact_id', 'it_product_id', name=op.f('vendor_contact_products_pkey')),
    )

    # Keep vendor text untouched for contracts, interactions and reports. Existing equivalent
    # vendor spellings share one company after whitespace/case normalisation.
    connection = op.get_bind()
    vendors = connection.execute(sa.text('SELECT DISTINCT vendor FROM it_products ORDER BY vendor')).scalars()
    company_ids = {}
    for vendor in vendors:
        name = ' '.join(vendor.split())
        if not name:
            continue
        key = name.casefold().replace('ё', 'е')
        company_id = company_ids.get(key)
        if company_id is None:
            company_id = connection.execute(
                sa.text('INSERT INTO vendor_companies (name) VALUES (:name) RETURNING id'), {'name': name},
            ).scalar_one()
            company_ids[key] = company_id
        connection.execute(
            sa.text('UPDATE it_products SET company_id = :company_id WHERE vendor = :vendor'),
            {'company_id': company_id, 'vendor': vendor},
        )


def downgrade() -> None:
    op.drop_table('vendor_contact_products')
    op.drop_index(op.f('ix_vendor_contacts_company_id'), table_name='vendor_contacts')
    op.drop_table('vendor_contacts')
    op.drop_index(op.f('ix_it_products_company_id'), table_name='it_products')
    op.drop_constraint(op.f('it_products_company_id_fkey'), 'it_products', type_='foreignkey')
    op.drop_column('it_products', 'company_id')
    op.drop_table('vendor_companies')
