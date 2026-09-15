"""workflows

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-16

Configurable workflows (docs/design/workflows.md, decisions D-149–D-154). Creates the default template from the
statuses the application used so far, points every launch at its current status, and copies stage history into
status_changes. The old stage_events table is left untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Copied rather than imported: a migration must keep producing the same data if application code changes later.
DEFAULT_TEMPLATE = 'Типовое взаимодействие с вузом'
DEFAULT_DESCRIPTION = 'Базовый процесс из технического задания: от поиска контакта до повышения квалификации преподавателей.'
DEFAULT_STATUSES = [
    'Поиск контакта', 'Уточнение интереса', 'Встреча', 'Обмен документами', 'Согласование документов', 'Подписание',
    'Передача материалов и лицензий', 'Внедрение продукта', 'Обучение преподавателей', 'Актуализация программы',
    'Проведение занятий', 'Обновление материалов', 'Повышение квалификации',
]


def upgrade() -> None:
    op.create_table(
        'workflow_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('workflow_templates_pkey')),
        sa.UniqueConstraint('name', name=op.f('workflow_templates_name_key')),
    )
    op.create_table(
        'workflow_statuses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120, collation='ru-RU-x-icu'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('is_final', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['workflow_templates.id'], name=op.f('workflow_statuses_template_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('workflow_statuses_pkey')),
        sa.UniqueConstraint('template_id', 'name', name=op.f('workflow_statuses_template_id_key')),
    )
    op.create_index(op.f('ix_workflow_statuses_template_id'), 'workflow_statuses', ['template_id'], unique=False)
    op.create_table(
        'status_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('launch_id', sa.Integer(), nullable=False),
        sa.Column('from_status_id', sa.Integer(), nullable=True),
        sa.Column('to_status_id', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['from_status_id'], ['workflow_statuses.id'], name=op.f('status_changes_from_status_id_fkey')),
        sa.ForeignKeyConstraint(['launch_id'], ['launches.id'], name=op.f('status_changes_launch_id_fkey')),
        sa.ForeignKeyConstraint(['to_status_id'], ['workflow_statuses.id'], name=op.f('status_changes_to_status_id_fkey')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('status_changes_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('status_changes_pkey')),
    )
    op.create_index(op.f('ix_status_changes_launch_id'), 'status_changes', ['launch_id'], unique=False)
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status_change_id', sa.Integer(), nullable=False),
        sa.Column('launch_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('storage_key', sa.String(length=64), nullable=False),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['launch_id'], ['launches.id'], name=op.f('attachments_launch_id_fkey')),
        sa.ForeignKeyConstraint(['status_change_id'], ['status_changes.id'], name=op.f('attachments_status_change_id_fkey')),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('attachments_uploaded_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('attachments_pkey')),
        sa.UniqueConstraint('storage_key', name=op.f('attachments_storage_key_key')),
    )
    op.create_index(op.f('ix_attachments_launch_id'), 'attachments', ['launch_id'], unique=False)
    op.create_index(op.f('ix_attachments_status_change_id'), 'attachments', ['status_change_id'], unique=False)

    op.add_column('launches', sa.Column('workflow_template_id', sa.Integer(), nullable=True))
    op.add_column('launches', sa.Column('status_id', sa.Integer(), nullable=True))
    op.create_foreign_key(op.f('launches_workflow_template_id_fkey'), 'launches', 'workflow_templates', ['workflow_template_id'], ['id'])
    op.create_foreign_key(op.f('launches_status_id_fkey'), 'launches', 'workflow_statuses', ['status_id'], ['id'])

    connection = op.get_bind()
    template_id = connection.execute(
        sa.text('insert into workflow_templates (name, description, is_default) values (:name, :description, true) returning id'),
        {'name': DEFAULT_TEMPLATE, 'description': DEFAULT_DESCRIPTION},
    ).scalar_one()
    for position, name in enumerate(DEFAULT_STATUSES):
        connection.execute(
            sa.text('insert into workflow_statuses (template_id, name, position, is_final) values (:template_id, :name, :position, :is_final)'),
            {'template_id': template_id, 'name': name, 'position': position, 'is_final': position == len(DEFAULT_STATUSES) - 1},
        )
    connection.execute(sa.text("""
        update launches
        set workflow_template_id = :template_id,
            status_id = (select id from workflow_statuses s where s.template_id = :template_id and s.position = launches.stage)
    """), {'template_id': template_id})
    # Each copied event records the previous stage of the same launch as its starting status.
    connection.execute(sa.text("""
        insert into status_changes (launch_id, from_status_id, to_status_id, comment, created_at)
        select e.launch_id,
               lag(s.id) over (partition by e.launch_id order by e.created_at, e.id),
               s.id, '', e.created_at
        from stage_events e
        join workflow_statuses s on s.template_id = :template_id and s.position = e.stage
        order by e.launch_id, e.created_at, e.id
    """), {'template_id': template_id})

    op.alter_column('launches', 'workflow_template_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('launches', 'status_id', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.drop_constraint(op.f('launches_status_id_fkey'), 'launches', type_='foreignkey')
    op.drop_constraint(op.f('launches_workflow_template_id_fkey'), 'launches', type_='foreignkey')
    op.drop_column('launches', 'status_id')
    op.drop_column('launches', 'workflow_template_id')
    op.drop_index(op.f('ix_attachments_status_change_id'), table_name='attachments')
    op.drop_index(op.f('ix_attachments_launch_id'), table_name='attachments')
    op.drop_table('attachments')
    op.drop_index(op.f('ix_status_changes_launch_id'), table_name='status_changes')
    op.drop_table('status_changes')
    op.drop_index(op.f('ix_workflow_statuses_template_id'), table_name='workflow_statuses')
    op.drop_table('workflow_statuses')
    op.drop_table('workflow_templates')
