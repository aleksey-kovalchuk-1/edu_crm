"""Organization card (Настройки → Организация) with the owner's details.

Revision ID: 0026
Revises: 0025
"""
from datetime import date

from alembic import op
import sqlalchemy as sa

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None

RU = 'ru-RU-x-icu'
LEGAL_ADDRESS = '108811, г. Москва, Киевское шоссе, 22-й км, домовладение 6, стр. 1, офис Е434'


def upgrade() -> None:
    table = op.create_table(
        'organization_profile',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200, collation=RU), nullable=False),
        sa.Column('legal_name', sa.String(500, collation=RU), nullable=False),
        sa.Column('ogrn', sa.String(13), nullable=False),
        sa.Column('registration_date', sa.Date(), nullable=False),
        sa.Column('legal_address', sa.String(500), nullable=False),
        sa.Column('postal_address', sa.String(500), nullable=False),
        sa.Column('contact_address', sa.String(500), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.CheckConstraint('id = 1', name=op.f('organization_profile_single_row_check')),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('organization_profile_updated_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('organization_profile_pkey')),
    )
    # The owner's details (request of 27.09.2026), so the card is filled from the first release.
    op.bulk_insert(table, [{
        'id': 1,
        'name': 'ИТ Школа Ростелеком',
        'legal_name': 'Общество с ограниченной ответственностью «Ростелеком Информационные Технологии»',
        'ogrn': '1095030001131',
        'registration_date': date(2009, 4, 10),
        'legal_address': LEGAL_ADDRESS,
        'postal_address': LEGAL_ADDRESS,
        'contact_address': 'Москва, проспект Вернадского, д. 41',
        'phone': '+74951966205',
        'email': 'edupro@rt.ru',
    }])


def downgrade() -> None:
    op.drop_table('organization_profile')
