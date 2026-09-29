"""Remove the archived customer-data features for good (owner 2026-09-29, D-248; archived by D-235/D-236).

Drops the learner questionnaires, their fingerprints, the old customer-import batches and row links, the fraud
alerts, and the learner link of course applications (applications from the customer's JSON never had one, D-247).
Vendor companies and contacts and course applications stay. The upgrade refuses to run while any dropped table
still holds rows, so no data is removed silently; production had none on 2026-09-29.

Revision ID: 0031
Revises: 0030
"""
import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None

DROPPED = ('fraud_alerts', 'customer_import_row_links', 'customer_import_batches', 'learner_fingerprints', 'learners')


def upgrade() -> None:
    connection = op.get_bind()
    filled = [table for table in DROPPED
              if connection.execute(sa.text(f'select exists (select 1 from {table})')).scalar()]
    if connection.execute(sa.text('select exists (select 1 from course_applications where learner_id is not null)')).scalar():
        filled.append('course_applications.learner_id')
    if filled:
        raise RuntimeError('Archived customer data is still present, nothing was dropped: ' + ', '.join(filled))

    op.drop_index(op.f('ix_course_applications_learner_id'), table_name='course_applications')
    op.drop_constraint(op.f('course_applications_learner_id_fkey'), 'course_applications', type_='foreignkey')
    op.drop_column('course_applications', 'learner_id')
    for table in DROPPED:
        op.drop_table(table)


def _original(name):
    # The creating migrations are fixed files, so reusing their definitions keeps the downgrade exact.
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(f'_edu_crm_{path.stem}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def downgrade() -> None:
    for name in ('0019_learners.py', '0021_customer_import_batches.py', '0022_fraud_alerts.py',
                 '0023_learner_fingerprints.py'):
        _original(name).upgrade()
    # Nullable, as after 0030: applications imported since then have no learner.
    op.add_column('course_applications', sa.Column('learner_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('course_applications_learner_id_fkey'), 'course_applications', 'learners',
                          ['learner_id'], ['id'])
    op.create_index(op.f('ix_course_applications_learner_id'), 'course_applications', ['learner_id'])
