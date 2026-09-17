"""reports

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-17

One row per `report_generate` background job (T-050-T-052, D-180+): the generated file's storage key,
format and size. Reports reuse the existing `background_jobs` queue (D-166) without a schema change to
that table; this migration only adds the small table that tracks the resulting file.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REPORT_FORMATS = ('xlsx', 'xls', 'pdf', 'json')


def upgrade() -> None:
    op.create_table(
        'report_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('format', sa.String(length=10), nullable=False),
        sa.Column('storage_key', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f"format in ({', '.join(repr(f) for f in REPORT_FORMATS)})", name=op.f('report_files_format_check')),
        sa.ForeignKeyConstraint(['job_id'], ['background_jobs.id'], name=op.f('report_files_job_id_fkey')),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('report_files_created_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('report_files_pkey')),
        sa.UniqueConstraint('job_id', name=op.f('report_files_job_id_key')),
        sa.UniqueConstraint('storage_key', name=op.f('report_files_storage_key_key')),
    )
    op.create_index(op.f('ix_report_files_created_at'), 'report_files', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_report_files_created_at'), table_name='report_files')
    op.drop_table('report_files')
