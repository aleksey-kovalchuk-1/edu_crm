"""Centralised task permission policy (docs/design/tasks.md).

Task participation (creator / assignee / co-executor / observer) and CRM-wide roles (`crm-user`,
`crm-supervisor`, `crm-admin`) are separate dimensions; every route asks `can()` or filters through
`visible_tasks_query()` instead of checking role names itself. The action set matches the one a
future Settings > "Пользователи и роли" matrix would need to configure (`TaskAction`), so that later
work can replace the body of `can()` with a data-driven lookup without changing any call site.
"""
from enum import StrEnum

from sqlalchemy import exists, or_, select, true

from .catalog_routes import managed_university_ids, sees_all
from .models import Task, TaskMember


class TaskAction(StrEnum):
    VIEW = 'view'
    CREATE = 'create'
    EDIT = 'edit'
    REASSIGN = 'reassign'
    CHANGE_DEADLINE = 'change_deadline'
    COMPLETE = 'complete'
    REOPEN = 'reopen'
    ARCHIVE = 'archive'
    EDIT_CHECKLIST = 'edit_checklist'
    MANAGE_TEMPLATES = 'manage_templates'
    EXPORT = 'export'
    MANAGE_PERMISSIONS = 'manage_permissions'


# Actions any signed-in CRM user may take without any task-specific relationship (creating a task,
# exporting their own visible list, ...). Every other action needs `_related` or a supervisor/admin role.
GLOBAL_ACTIONS = frozenset({TaskAction.CREATE, TaskAction.EXPORT})

# Actions reserved for crm-supervisor / crm-admin regardless of the caller's relationship to the task.
MANAGEMENT_ONLY_ACTIONS = frozenset({TaskAction.MANAGE_TEMPLATES, TaskAction.MANAGE_PERMISSIONS})

# Actions a task's own creator may take on it, alongside a supervisor/admin in scope.
CREATOR_ACTIONS = frozenset({
    TaskAction.EDIT, TaskAction.REASSIGN, TaskAction.CHANGE_DEADLINE, TaskAction.ARCHIVE,
    TaskAction.REOPEN, TaskAction.EDIT_CHECKLIST,
})

# Actions an assignee may take on a task they are assigned to, alongside the creator/supervisor/admin.
ASSIGNEE_ACTIONS = frozenset({TaskAction.COMPLETE, TaskAction.EDIT_CHECKLIST})


def _member_roles(task, user):
    session = task._sa_instance_state.session
    if session is None:
        return frozenset()
    rows = session.execute(
        select(TaskMember.role).where(TaskMember.task_id == task.id, TaskMember.user_id == user.id)
    ).scalars().all()
    return frozenset(rows)


def _in_university_scope(user, task):
    if task.university_id is None:
        return False
    session = task._sa_instance_state.session
    if session is None:
        return False
    return bool(session.scalar(select(exists().where(
        Task.id == task.id, Task.university_id.in_(managed_university_ids(user)),
    ))))


def can(user, action, task=None):
    """Whether `user` may take `action`, on `task` when one applies."""
    if sees_all(user):
        return True
    if action in MANAGEMENT_ONLY_ACTIONS:
        return False
    if task is None:
        return action in GLOBAL_ACTIONS
    if action in GLOBAL_ACTIONS:
        return True

    is_creator = task.creator_id == user.id
    roles = _member_roles(task, user)
    is_assignee = 'assignee' in roles
    related = is_creator or bool(roles) or _in_university_scope(user, task)

    if action == TaskAction.VIEW:
        return related
    if not related:
        return False
    if is_creator and action in CREATOR_ACTIONS:
        return True
    if is_assignee and action in ASSIGNEE_ACTIONS:
        return True
    return False


def visible_tasks_query(user):
    """A WHERE clause for `select(Task)...` (or any query selecting from `Task`) limited to what `user` may view."""
    if sees_all(user):
        return true()
    return or_(
        Task.creator_id == user.id,
        Task.university_id.in_(managed_university_ids(user)),
        exists().where(TaskMember.task_id == Task.id, TaskMember.user_id == user.id),
    )
