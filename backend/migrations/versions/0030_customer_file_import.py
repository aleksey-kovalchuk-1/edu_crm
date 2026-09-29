"""Customer files in «Загрузка справочников» (2026-09-29, D-247).

Applications imported from the customer's JSON carry no learner (no personal data is kept), the import record says
which importer read the file, and universities, IT directions and IT products keep the customer workbook's stable IDs.

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None

EXTERNAL_ID_TABLES = ('universities', 'it_directions', 'it_products')


def upgrade() -> None:
    op.alter_column('course_applications', 'learner_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('catalog_imports', sa.Column('kind', sa.String(20), nullable=False, server_default='catalog'))
    op.create_check_constraint(op.f('catalog_imports_kind_check'), 'catalog_imports', "kind in ('catalog', 'applications', 'workbook')")
    op.add_column('catalog_imports', sa.Column('sheets', postgresql.JSONB(), nullable=True))
    for table in EXTERNAL_ID_TABLES:
        op.add_column(table, sa.Column('external_id', sa.String(64), nullable=True))
        op.create_unique_constraint(op.f(f'{table}_external_id_key'), table, ['external_id'])


def downgrade() -> None:
    for table in EXTERNAL_ID_TABLES:
        op.drop_constraint(op.f(f'{table}_external_id_key'), table, type_='unique')
        op.drop_column(table, 'external_id')
    op.drop_column('catalog_imports', 'sheets')
    op.drop_constraint(op.f('catalog_imports_kind_check'), 'catalog_imports', type_='check')
    op.drop_column('catalog_imports', 'kind')
    # Applications imported without a learner cannot satisfy the old NOT NULL; they are removed on downgrade.
    op.execute('delete from course_applications where learner_id is null')
    op.alter_column('course_applications', 'learner_id', existing_type=sa.Integer(), nullable=False)
