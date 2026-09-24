"""link interactions to the IT product catalog (reports: filter by IT product / direction)

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: existing interactions keep their free-text `product` until someone links them (D-221).
    op.add_column('launches', sa.Column('it_product_id', sa.Integer(), sa.ForeignKey('it_products.id'), nullable=True))
    op.create_index('ix_launches_it_product_id', 'launches', ['it_product_id'])


def downgrade() -> None:
    op.drop_index('ix_launches_it_product_id', table_name='launches')
    op.drop_column('launches', 'it_product_id')
