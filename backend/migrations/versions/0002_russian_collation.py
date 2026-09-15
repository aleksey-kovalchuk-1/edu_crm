"""russian collation for text columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

Russian names are compared and sorted with the ICU collation "ru-RU-x-icu" set per column.
Setting it per column works on existing databases; changing the cluster locale would require
re-initialising the data volume, which is not allowed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RUSSIAN_COLLATION = 'ru-RU-x-icu'
COLUMNS = [
    ('universities', 'name', 200),
    ('universities', 'city', 100),
    ('universities', 'contact', 200),
    ('launches', 'program', 200),
    ('launches', 'product', 200),
    ('launches', 'owner', 100),
    ('tasks', 'title', 200),
    ('tasks', 'owner', 100),
]


def upgrade() -> None:
    for table, column, length in COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.String(length, collation=RUSSIAN_COLLATION),
            existing_type=sa.String(length),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Without a COLLATE clause PostgreSQL restores the type's default collation.
    for table, column, length in COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.String(length),
            existing_type=sa.String(length, collation=RUSSIAN_COLLATION),
            existing_nullable=False,
        )
