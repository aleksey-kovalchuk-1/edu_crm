"""tasks workspace

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-19

First slice of the Tasks workspace redesign (docs/design/tasks.md, decisions D-158-D-161). Extends the
placeholder `tasks` table (`launch_id`, `title`, `owner`, `deadline`, `done`) in place instead of
replacing it, so every existing task row survives:

- `status` backfills from `done` (`completed` / `new`); `priority` defaults to `normal`.
- `creator_id` is matched from the free-text `owner` to exactly one active CRM user by
  case/whitespace-insensitive full name; ambiguous or unmatched rows keep `creator_id` NULL and the
  original `owner` text untouched, which is the review signal for an administrator (no separate flag).
- `launch_id` (the optional "interaction" link) and `deadline` become nullable; every existing row
  keeps its current value.
- `owner` and `done` are not dropped or written to by new code, but stay in the database and keep
  working for the legacy `GET/PATCH /api/v1/tasks` endpoints until they are replaced in a later slice.

Adds the supporting tables for members (assignees/participants/observers), checklist items, tags,
comments, attachments, the per-task activity timeline, task plan templates and their generated runs,
and per-user view preferences.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RU = 'ru-RU-x-icu'


def upgrade() -> None:
    # ---------- task plan templates (created before `tasks` so origin_plan_run_id can reference them) ----------
    op.create_table(
        'task_plan_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200, collation=RU), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('task_plan_templates_created_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_plan_templates_pkey')),
        sa.UniqueConstraint('name', name=op.f('task_plan_templates_name_key')),
    )

    op.create_table(
        'task_plan_template_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200, collation=RU), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('assignee_rule', sa.String(length=30), nullable=False),
        sa.Column('assignee_rule_user_id', sa.Integer(), nullable=True),
        sa.Column('start_offset_days', sa.Integer(), server_default='0', nullable=False),
        sa.Column('deadline_offset_days', sa.Integer(), nullable=True),
        sa.Column('offset_unit', sa.String(length=10), server_default='calendar', nullable=False),
        sa.Column('priority', sa.String(length=10), server_default='normal', nullable=False),
        sa.Column('approval_required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_optional', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('depends_on_step_id', sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "assignee_rule in ('specific_user', 'interaction_owner', 'university_manager', 'plan_creator', 'manual')",
            name=op.f('task_plan_template_steps_assignee_rule_check'),
        ),
        sa.CheckConstraint("offset_unit in ('calendar', 'business')", name=op.f('task_plan_template_steps_offset_unit_check')),
        sa.ForeignKeyConstraint(['template_id'], ['task_plan_templates.id'], name=op.f('task_plan_template_steps_template_id_fkey')),
        sa.ForeignKeyConstraint(['assignee_rule_user_id'], ['users.id'], name=op.f('task_plan_template_steps_assignee_rule_user_id_fkey')),
        sa.ForeignKeyConstraint(['depends_on_step_id'], ['task_plan_template_steps.id'], name=op.f('task_plan_template_steps_depends_on_step_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_plan_template_steps_pkey')),
        sa.UniqueConstraint('template_id', 'position', name=op.f('task_plan_template_steps_template_id_key')),
    )
    op.create_index(op.f('ix_task_plan_template_steps_template_id'), 'task_plan_template_steps', ['template_id'], unique=False)

    op.create_table(
        'task_plan_template_step_checklist_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('step_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200, collation=RU), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['step_id'], ['task_plan_template_steps.id'], name=op.f('task_plan_template_step_checklist_items_step_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_plan_template_step_checklist_items_pkey')),
    )
    op.create_index(op.f('ix_task_plan_template_step_checklist_items_step_id'), 'task_plan_template_step_checklist_items', ['step_id'], unique=False)

    op.create_table(
        'task_plan_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        # Full copy of the template and its steps at generation time: later template edits must never
        # rewrite tasks a past run already created (docs/design/tasks.md).
        sa.Column('template_snapshot', JSONB(), nullable=False),
        sa.Column('university_id', sa.Integer(), nullable=False),
        sa.Column('launch_id', sa.Integer(), nullable=True),
        sa.Column('started_by_user_id', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['task_plan_templates.id'], name=op.f('task_plan_runs_template_id_fkey')),
        sa.ForeignKeyConstraint(['university_id'], ['universities.id'], name=op.f('task_plan_runs_university_id_fkey')),
        sa.ForeignKeyConstraint(['launch_id'], ['launches.id'], name=op.f('task_plan_runs_launch_id_fkey')),
        sa.ForeignKeyConstraint(['started_by_user_id'], ['users.id'], name=op.f('task_plan_runs_started_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_plan_runs_pkey')),
    )
    op.create_index(op.f('ix_task_plan_runs_template_id'), 'task_plan_runs', ['template_id'], unique=False)
    op.create_index(op.f('ix_task_plan_runs_university_id'), 'task_plan_runs', ['university_id'], unique=False)

    # ---------- extend the existing `tasks` table ----------
    op.add_column('tasks', sa.Column('description', sa.Text(), server_default='', nullable=False))
    op.add_column('tasks', sa.Column('status', sa.String(length=20), server_default='new', nullable=False))
    op.add_column('tasks', sa.Column('priority', sa.String(length=10), server_default='normal', nullable=False))
    op.add_column('tasks', sa.Column('planned_start', sa.Date(), nullable=True))
    op.add_column('tasks', sa.Column('creator_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('university_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('contract_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('parent_task_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('approval_required', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('tasks', sa.Column('require_checklist_complete', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('tasks', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tasks', sa.Column('completed_by_user_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tasks', sa.Column('archived_by_user_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('origin_plan_run_id', sa.Integer(), nullable=True))
    op.add_column('tasks', sa.Column('origin_template_step_key', sa.String(length=64), nullable=True))
    op.add_column('tasks', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('tasks', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('tasks', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.alter_column('tasks', 'launch_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('tasks', 'deadline', existing_type=sa.Date(), nullable=True)
    # `owner`/`done` stay NOT NULL (existing rows, existing legacy endpoints) but a new task created
    # through the new API never sets them, so they need a default to satisfy that constraint.
    op.alter_column('tasks', 'owner', existing_type=sa.String(length=100), server_default='')
    op.alter_column('tasks', 'done', existing_type=sa.Boolean(), server_default=sa.text('false'))

    op.create_check_constraint(
        op.f('tasks_status_check'), 'tasks',
        "status in ('new', 'in_progress', 'awaiting_review', 'completed', 'deferred', 'cancelled')",
    )
    op.create_check_constraint(
        op.f('tasks_priority_check'), 'tasks', "priority in ('low', 'normal', 'high', 'urgent')",
    )
    op.create_check_constraint(op.f('tasks_no_self_parent_check'), 'tasks', 'parent_task_id != id')

    op.create_foreign_key(op.f('tasks_creator_id_fkey'), 'tasks', 'users', ['creator_id'], ['id'])
    op.create_foreign_key(op.f('tasks_university_id_fkey'), 'tasks', 'universities', ['university_id'], ['id'])
    op.create_foreign_key(op.f('tasks_contract_id_fkey'), 'tasks', 'contracts', ['contract_id'], ['id'])
    op.create_foreign_key(op.f('tasks_parent_task_id_fkey'), 'tasks', 'tasks', ['parent_task_id'], ['id'])
    op.create_foreign_key(op.f('tasks_completed_by_user_id_fkey'), 'tasks', 'users', ['completed_by_user_id'], ['id'])
    op.create_foreign_key(op.f('tasks_archived_by_user_id_fkey'), 'tasks', 'users', ['archived_by_user_id'], ['id'])
    op.create_foreign_key(op.f('tasks_origin_plan_run_id_fkey'), 'tasks', 'task_plan_runs', ['origin_plan_run_id'], ['id'])

    op.create_index(op.f('ix_tasks_launch_id'), 'tasks', ['launch_id'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    op.create_index(op.f('ix_tasks_deadline'), 'tasks', ['deadline'], unique=False)
    op.create_index(op.f('ix_tasks_creator_id'), 'tasks', ['creator_id'], unique=False)
    op.create_index(op.f('ix_tasks_university_id'), 'tasks', ['university_id'], unique=False)
    op.create_index(op.f('ix_tasks_contract_id'), 'tasks', ['contract_id'], unique=False)
    op.create_index(op.f('ix_tasks_parent_task_id'), 'tasks', ['parent_task_id'], unique=False)
    op.create_index(op.f('ix_tasks_archived_at'), 'tasks', ['archived_at'], unique=False)

    # ---------- members, checklist, tags, comments, attachments, activity ----------
    op.create_table(
        'task_members',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role in ('assignee', 'participant', 'observer')", name=op.f('task_members_role_check')),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('task_members_task_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('task_members_user_id_fkey')),
        sa.PrimaryKeyConstraint('task_id', 'user_id', 'role', name=op.f('task_members_pkey')),
    )
    op.create_index(op.f('ix_task_members_user_id'), 'task_members', ['user_id'], unique=False)

    op.create_table(
        'task_checklist_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200, collation=RU), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('is_done', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('assignee_user_id', sa.Integer(), nullable=True),
        sa.Column('deadline', sa.Date(), nullable=True),
        sa.Column('completed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('task_checklist_items_task_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assignee_user_id'], ['users.id'], name=op.f('task_checklist_items_assignee_user_id_fkey')),
        sa.ForeignKeyConstraint(['completed_by_user_id'], ['users.id'], name=op.f('task_checklist_items_completed_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_checklist_items_pkey')),
        sa.UniqueConstraint('task_id', 'position', name=op.f('task_checklist_items_task_id_key')),
    )
    op.create_index(op.f('ix_task_checklist_items_task_id'), 'task_checklist_items', ['task_id'], unique=False)

    op.create_table(
        'task_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60, collation=RU), nullable=False),
        sa.Column('color', sa.String(length=20), server_default='', nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('task_tags_pkey')),
        sa.UniqueConstraint('name', name=op.f('task_tags_name_key')),
    )

    op.create_table(
        'task_tag_links',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('task_tag_links_task_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['task_tags.id'], name=op.f('task_tag_links_tag_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('task_id', 'tag_id', name=op.f('task_tag_links_pkey')),
    )
    op.create_index(op.f('ix_task_tag_links_tag_id'), 'task_tag_links', ['tag_id'], unique=False)

    op.create_table(
        'task_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('author_user_id', sa.Integer(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('task_comments_task_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], name=op.f('task_comments_author_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_comments_pkey')),
    )
    op.create_index(op.f('ix_task_comments_task_id'), 'task_comments', ['task_id'], unique=False)

    op.create_table(
        'task_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('comment_id', sa.Integer(), nullable=True),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('storage_key', sa.String(length=64), nullable=False),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('task_attachments_task_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['comment_id'], ['task_comments.id'], name=op.f('task_attachments_comment_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], name=op.f('task_attachments_uploaded_by_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_attachments_pkey')),
        sa.UniqueConstraint('storage_key', name=op.f('task_attachments_storage_key_key')),
    )
    op.create_index(op.f('ix_task_attachments_task_id'), 'task_attachments', ['task_id'], unique=False)
    op.create_index(op.f('ix_task_attachments_comment_id'), 'task_attachments', ['comment_id'], unique=False)

    op.create_table(
        'task_events',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('from_value', sa.String(length=100), nullable=True),
        sa.Column('to_value', sa.String(length=100), nullable=True),
        sa.Column('comment', sa.Text(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name=op.f('task_events_task_id_fkey'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('task_events_actor_user_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('task_events_pkey')),
    )
    op.create_index(op.f('ix_task_events_task_id'), 'task_events', ['task_id'], unique=False)
    op.create_index(op.f('ix_task_events_created_at'), 'task_events', ['created_at'], unique=False)

    op.create_table(
        'task_user_preferences',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('list_columns', JSONB(), nullable=True),
        sa.Column('planner_columns', JSONB(), nullable=True),
        sa.Column('planner_positions', JSONB(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('task_user_preferences_user_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', name=op.f('task_user_preferences_pkey')),
    )

    # ---------- data backfill ----------
    connection = op.get_bind()
    connection.execute(sa.text("update tasks set status = case when done then 'completed' else 'new' end"))
    connection.execute(sa.text("""
        with matches as (
            select t.id as task_id, u.id as user_id
            from tasks t
            join users u on u.is_active and lower(trim(u.full_name)) = lower(trim(t.owner))
            where coalesce(trim(t.owner), '') != ''
        ),
        unique_matches as (
            select task_id, min(user_id) as user_id
            from matches
            group by task_id
            having count(*) = 1
        )
        update tasks t set creator_id = um.user_id
        from unique_matches um
        where t.id = um.task_id
    """))


def downgrade() -> None:
    op.drop_table('task_user_preferences')
    op.drop_index(op.f('ix_task_events_created_at'), table_name='task_events')
    op.drop_index(op.f('ix_task_events_task_id'), table_name='task_events')
    op.drop_table('task_events')
    op.drop_index(op.f('ix_task_attachments_comment_id'), table_name='task_attachments')
    op.drop_index(op.f('ix_task_attachments_task_id'), table_name='task_attachments')
    op.drop_table('task_attachments')
    op.drop_index(op.f('ix_task_comments_task_id'), table_name='task_comments')
    op.drop_table('task_comments')
    op.drop_index(op.f('ix_task_tag_links_tag_id'), table_name='task_tag_links')
    op.drop_table('task_tag_links')
    op.drop_table('task_tags')
    op.drop_index(op.f('ix_task_checklist_items_task_id'), table_name='task_checklist_items')
    op.drop_table('task_checklist_items')
    op.drop_index(op.f('ix_task_members_user_id'), table_name='task_members')
    op.drop_table('task_members')

    op.drop_index(op.f('ix_tasks_archived_at'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_parent_task_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_contract_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_university_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_creator_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_deadline'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_launch_id'), table_name='tasks')
    op.drop_constraint(op.f('tasks_origin_plan_run_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_archived_by_user_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_completed_by_user_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_parent_task_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_contract_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_university_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_creator_id_fkey'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('tasks_no_self_parent_check'), 'tasks', type_='check')
    op.drop_constraint(op.f('tasks_priority_check'), 'tasks', type_='check')
    op.drop_constraint(op.f('tasks_status_check'), 'tasks', type_='check')
    op.alter_column('tasks', 'done', existing_type=sa.Boolean(), server_default=None)
    op.alter_column('tasks', 'owner', existing_type=sa.String(length=100), server_default=None)
    op.alter_column('tasks', 'deadline', existing_type=sa.Date(), nullable=False)
    op.alter_column('tasks', 'launch_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('tasks', 'version')
    op.drop_column('tasks', 'updated_at')
    op.drop_column('tasks', 'created_at')
    op.drop_column('tasks', 'origin_template_step_key')
    op.drop_column('tasks', 'origin_plan_run_id')
    op.drop_column('tasks', 'archived_by_user_id')
    op.drop_column('tasks', 'archived_at')
    op.drop_column('tasks', 'completed_by_user_id')
    op.drop_column('tasks', 'completed_at')
    op.drop_column('tasks', 'require_checklist_complete')
    op.drop_column('tasks', 'approval_required')
    op.drop_column('tasks', 'parent_task_id')
    op.drop_column('tasks', 'contract_id')
    op.drop_column('tasks', 'university_id')
    op.drop_column('tasks', 'creator_id')
    op.drop_column('tasks', 'planned_start')
    op.drop_column('tasks', 'priority')
    op.drop_column('tasks', 'status')
    op.drop_column('tasks', 'description')

    op.drop_index(op.f('ix_task_plan_runs_university_id'), table_name='task_plan_runs')
    op.drop_index(op.f('ix_task_plan_runs_template_id'), table_name='task_plan_runs')
    op.drop_table('task_plan_runs')
    op.drop_index(op.f('ix_task_plan_template_step_checklist_items_step_id'), table_name='task_plan_template_step_checklist_items')
    op.drop_table('task_plan_template_step_checklist_items')
    op.drop_index(op.f('ix_task_plan_template_steps_template_id'), table_name='task_plan_template_steps')
    op.drop_table('task_plan_template_steps')
    op.drop_table('task_plan_templates')
