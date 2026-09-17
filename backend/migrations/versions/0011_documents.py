"""documents

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-16

Versioned document library linked to universities, interactions or contracts (D-169), separate from the
workflow `attachments` table (T-042), which is one file per status-change event with no versioning.

Renumbered during integration from 0010 -> 0011; see 0010_ingestion_foundation.py's docstring.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCUMENT_ENTITY_TYPES = ('university', 'launch', 'contract')
DOCUMENT_VERSION_STATES = ('uploaded', 'quarantined', 'validated', 'rejected', 'linked')
SCAN_RESULTS = ('pending', 'clean', 'infected', 'error', 'not_scanned')


def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=300, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('doc_type', sa.String(length=50), server_default='', nullable=False),
        sa.Column('academic_year', sa.String(length=20), server_default='', nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=200, collation='ru-RU-x-icu'), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f"entity_type in ({', '.join(repr(s) for s in DOCUMENT_ENTITY_TYPES)})", name=op.f('documents_entity_type_check')),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], name=op.f('documents_owner_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('documents_pkey')),
    )
    op.create_index('ix_documents_entity', 'documents', ['entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_documents_created_at'), 'documents', ['created_at'], unique=False)

    op.create_table(
        'document_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=64), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('state', sa.String(length=20), server_default='uploaded', nullable=False),
        sa.Column('scan_result', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f"state in ({', '.join(repr(s) for s in DOCUMENT_VERSION_STATES)})", name=op.f('document_versions_state_check')),
        sa.CheckConstraint(f"scan_result in ({', '.join(repr(s) for s in SCAN_RESULTS)})", name=op.f('document_versions_scan_result_check')),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('document_versions_document_id_fkey')),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('document_versions_uploaded_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('document_versions_pkey')),
        sa.UniqueConstraint('document_id', 'version_number', name=op.f('document_versions_document_id_key')),
        sa.UniqueConstraint('storage_key', name=op.f('document_versions_storage_key_key')),
    )
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_versions_created_at'), 'document_versions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('document_versions')
    op.drop_index('ix_documents_created_at', table_name='documents')
    op.drop_index('ix_documents_entity', table_name='documents')
    op.drop_table('documents')
