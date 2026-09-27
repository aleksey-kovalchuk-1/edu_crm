"""Turns committed model changes into notifications (spec 2026-09-27-notifications, «Механизм»).

Session listeners collect what changed (before_flush: attribute changes and deletions; after_flush: new
rows), and before_commit turns the collected changes into notifications in the same transaction, so a
rolled-back action leaves none and one action produces one notification per recipient and entity.
The acting user comes from session.info['actor_user_id'] (set when a request authenticates).
"""
from sqlalchemy import event, inspect, select

from .models import (
    Attachment, Contract, Launch, StatusChange, Task, TaskComment, TaskMember, University, UniversityContact,
    UniversityManager, WorkflowStatus,
)
from .notifications import notify

PENDING = 'notification_changes'
TRACKED_NEW = (UniversityManager, UniversityContact, StatusChange, TaskComment, TaskMember, Contract, WorkflowStatus)
TRACKED_DELETED = (UniversityManager, TaskMember)


def _changes(session):
    return session.info.setdefault(PENDING, [])


def _changed(obj, *names):
    state = inspect(obj)
    return {name: state.attrs[name].history for name in names if state.attrs[name].history.has_changes()}


def _before_flush(session, _context, _instances):
    changes = _changes(session)
    for obj in session.deleted:
        if isinstance(obj, TRACKED_DELETED):
            changes.append(('deleted', obj.__class__.__name__, _snapshot(obj)))
    for obj in session.dirty:
        if isinstance(obj, UniversityContact) and session.is_modified(obj, include_collections=False):
            changes.append(('updated', 'UniversityContact', {'university_id': obj.university_id, 'id': obj.id}))
        elif isinstance(obj, Task):
            history = _changed(obj, 'deadline', 'status')
            if history:
                changes.append(('updated', 'Task', {
                    'id': obj.id, 'deadline': history.get('deadline'), 'status': history.get('status'),
                }))
        elif isinstance(obj, Contract):
            history = _changed(obj, 'transfer_status')
            if history:
                changes.append(('updated', 'Contract', {'id': obj.id}))
        elif isinstance(obj, WorkflowStatus) and session.is_modified(obj, include_collections=False):
            changes.append(('updated', 'WorkflowStatus', {'template_id': obj.template_id}))


def _after_flush(session, _context):
    changes = _changes(session)
    for obj in session.new:
        if isinstance(obj, TRACKED_NEW):
            changes.append(('new', obj.__class__.__name__, _snapshot(obj)))


def _snapshot(obj):
    if isinstance(obj, UniversityManager):
        return {'university_id': obj.university_id, 'user_id': obj.user_id}
    if isinstance(obj, TaskMember):
        return {'task_id': obj.task_id, 'user_id': obj.user_id, 'role': obj.role}
    if isinstance(obj, UniversityContact):
        return {'university_id': obj.university_id, 'id': obj.id}
    if isinstance(obj, StatusChange):
        return {'id': obj.id}
    if isinstance(obj, TaskComment):
        return {'task_id': obj.task_id, 'author_user_id': obj.author_user_id}
    if isinstance(obj, Contract):
        return {'id': obj.id}
    if isinstance(obj, WorkflowStatus):
        return {'template_id': obj.template_id}
    return {}


def _before_commit(session):
    session.flush()  # collect changes still pending in the session
    changes = session.info.pop(PENDING, [])
    if not changes:
        return
    actor = session.info.get('actor_user_id')
    for handler in HANDLERS:
        handler(session, changes, actor)


def _reset(session):
    session.info.pop(PENDING, None)
    session.info.pop('notified', None)


def _do_orm_execute(state):
    """Task members are replaced with a bulk `delete(TaskMember)` the ORM hooks never see; record which rows
    it removes, so commit-time comparison can tell real removals from members that were simply re-added."""
    statement = state.statement
    if state.is_delete and getattr(getattr(statement, 'table', None), 'name', None) == 'task_members':
        query = select(TaskMember.task_id, TaskMember.user_id, TaskMember.role)
        if statement.whereclause is not None:
            query = query.where(statement.whereclause)
        rows = state.session.execute(query).all()
        _changes(state.session).extend(
            ('deleted', 'TaskMember', {'task_id': t, 'user_id': u, 'role': r}) for t, u, r in rows)


def install(session_factory):
    event.listen(session_factory, 'do_orm_execute', _do_orm_execute)
    event.listen(session_factory, 'before_flush', _before_flush)
    event.listen(session_factory, 'after_flush', _after_flush)
    event.listen(session_factory, 'before_commit', _before_commit)
    event.listen(session_factory, 'after_commit', _reset)
    event.listen(session_factory, 'after_rollback', _reset)


# ---------- handlers --------------------------------------------------------------------------

def university_managers(db, university_id):
    return db.scalars(select(UniversityManager.user_id).where(UniversityManager.university_id == university_id)).all()


def _university_events(db, changes, actor):
    names = {}

    def name_of(university_id):
        if university_id not in names:
            university = db.get(University, university_id)
            names[university_id] = university.name if university else ''
        return names[university_id]

    for kind, model, data in changes:
        if model == 'UniversityManager':
            assigned = kind == 'new'
            notify(db, user_id=data['user_id'], event_type='university_assigned' if assigned else 'university_unassigned',
                   title='Вас назначили ответственным за вуз' if assigned else 'Вас сняли с ответственности за вуз',
                   body=name_of(data['university_id']), link_type='university', link_id=data['university_id'],
                   university_id=data['university_id'], actor_user_id=actor)
        elif model == 'UniversityContact':
            for user_id in university_managers(db, data['university_id']):
                notify(db, user_id=user_id, event_type='university_contacts_changed',
                       title='Изменили контакты закреплённого за вами вуза', body=name_of(data['university_id']),
                       link_type='university', link_id=data['university_id'], university_id=data['university_id'],
                       actor_user_id=actor)


def _launch_events(db, changes, actor):
    for kind, model, data in changes:
        if kind != 'new' or model != 'StatusChange':
            continue
        change = db.get(StatusChange, data['id'])
        # from_status_id is NULL only for the entry written when an interaction is created: not a stage change.
        if change is None or change.from_status_id is None:
            continue
        launch = db.get(Launch, change.launch_id)
        if launch is None:
            continue
        moved = change.from_status_id != change.to_status_id
        target = db.get(WorkflowStatus, change.to_status_id)
        has_file = db.scalar(select(Attachment.id).where(Attachment.status_change_id == change.id).limit(1)) is not None
        # One action, one notification: the first type that applies and that the recipient has switched on.
        candidates = []
        if moved and target is not None and target.is_final:
            candidates.append(('launch_completed', f'Завершили взаимодействие «{launch.program}»'))
        if moved:
            candidates.append(('launch_stage_changed', f'«{launch.program}»: этап «{target.name if target else ""}»'))
        if change.comment or has_file:
            candidates.append(('launch_comment_or_file', f'К взаимодействию «{launch.program}» добавили комментарий или файл'))
        for user_id in university_managers(db, launch.university_id):
            for event_type, body in candidates:
                if notify(db, user_id=user_id, event_type=event_type, title=_LABEL[event_type], body=body,
                          link_type='launch', link_id=launch.id, university_id=launch.university_id, actor_user_id=actor):
                    break


def _workflow_events(db, changes, actor):
    template_ids = {data['template_id'] for kind, model, data in changes if model == 'WorkflowStatus'}
    for template_id in template_ids:
        # Each recipient gets one notification per action, linked to their first interaction on this process.
        rows = db.execute(
            select(UniversityManager.user_id, Launch.id, Launch.university_id)
            .join(Launch, Launch.university_id == UniversityManager.university_id)
            .where(Launch.workflow_template_id == template_id)
            .order_by(UniversityManager.user_id, Launch.id)
        ).all()
        first = {}
        for user_id, launch_id, university_id in rows:
            first.setdefault(user_id, (launch_id, university_id))
        for user_id, (launch_id, university_id) in first.items():
            notify(db, user_id=user_id, event_type='workflow_stages_changed', title=_LABEL['workflow_stages_changed'],
                   body='Изменили этапы процесса, по которому идут ваши взаимодействия', link_type='launch',
                   link_id=launch_id, university_id=university_id, actor_user_id=actor)


_LABEL = {
    'launch_completed': 'Взаимодействие завершено',
    'launch_stage_changed': 'Изменили этап взаимодействия',
    'launch_comment_or_file': 'Комментарий или файл к взаимодействию',
    'workflow_stages_changed': 'Изменили этапы процесса',
}

WORKING_ROLES = ('assignee', 'participant')


def task_member_ids(db, task_id, roles):
    return set(db.scalars(select(TaskMember.user_id).where(TaskMember.task_id == task_id, TaskMember.role.in_(roles))))


def _task_notify(db, task, user_ids, event_type, title, actor):
    for user_id in sorted(user_ids):
        notify(db, user_id=user_id, event_type=event_type, title=title, body=task.title, link_type='task',
               link_id=task.id, university_id=task.university_id, actor_user_id=actor)


def _task_events(db, changes, actor):
    deleted, inserted = {}, {}
    for kind, model, data in changes:
        if model == 'TaskMember':
            bucket = deleted if kind == 'deleted' else inserted
            bucket.setdefault(data['task_id'], set()).add((data['user_id'], data['role']))
    for task_id in sorted(set(deleted) | set(inserted)):
        task = db.get(Task, task_id)
        if task is None:
            continue
        now_rows = set(db.execute(select(TaskMember.user_id, TaskMember.role).where(TaskMember.task_id == task_id)).all())
        before_rows = (now_rows - inserted.get(task_id, set())) | deleted.get(task_id, set())
        working = lambda rows: {u for u, r in rows if r in WORKING_ROLES}  # noqa: E731
        after, before = working(now_rows), working(before_rows)
        _task_notify(db, task, after - before, 'task_assigned', 'Вас назначили исполнителем задачи', actor)
        _task_notify(db, task, before - after, 'task_unassigned', 'Вас убрали из исполнителей задачи', actor)

    for kind, model, data in changes:
        if model == 'Task' and kind == 'updated':
            task = db.get(Task, data['id'])
            if task is None:
                continue
            deadline, status = data['deadline'], data['status']
            # Checked against the current value: a change undone by a savepoint rollback sends nothing.
            if deadline and deadline.deleted and task.deadline != deadline.deleted[0]:
                _task_notify(db, task, task_member_ids(db, task.id, WORKING_ROLES), 'task_deadline_changed',
                             'Изменили срок вашей задачи', actor)
            if status and status.deleted and status.added and task.status == status.added[0]:
                old, new = status.deleted[0], status.added[0]
                if new == 'awaiting_review':
                    _task_notify(db, task, {task.creator_id} - {None}, 'task_submitted_for_approval',
                                 'Задачу отправили на согласование', actor)
                elif old == 'awaiting_review':
                    _task_notify(db, task, task_member_ids(db, task.id, WORKING_ROLES), 'task_review_decided',
                                 'Задачу согласовали' if new == 'completed' else 'Задачу вернули на доработку', actor)
                elif new in ('completed', 'cancelled'):
                    everyone = task_member_ids(db, task.id, ('assignee', 'participant', 'observer')) | {task.creator_id}
                    _task_notify(db, task, everyone - {None}, 'task_closed',
                                 'Задачу завершили' if new == 'completed' else 'Задачу отменили', actor)
        elif model == 'TaskComment' and kind == 'new':
            task = db.get(Task, data['task_id'])
            if task is not None:
                recipients = task_member_ids(db, task.id, WORKING_ROLES) | {task.creator_id}
                _task_notify(db, task, recipients - {None}, 'task_commented', 'Добавили комментарий к вашей задаче', actor)


def contract_recipients(db, contract):
    return set(university_managers(db, contract.university_id)) | ({contract.manager_user_id} - {None})


def _contract_events(db, changes, actor):
    from_import = db.info.get('notification_source') == 'import'
    for kind, model, data in changes:
        if model != 'Contract':
            continue
        contract = db.get(Contract, data['id'])
        if contract is None:
            continue
        if kind == 'new':
            if from_import:
                continue  # owner decision: imported contracts do not announce a signing
            event_type, title = 'contract_signed', 'Подписали договор по вашему вузу'
        else:
            event_type, title = 'contract_transfer_changed', 'Изменили статус передачи лицензий или материалов'
        for user_id in sorted(contract_recipients(db, contract)):
            # Contracts link to the university page: there is no «Договоры» navigation item.
            notify(db, user_id=user_id, event_type=event_type, title=title, body=f'Договор {contract.contract_number}',
                   link_type='contract', link_id=contract.id, university_id=contract.university_id, actor_user_id=actor)


HANDLERS = [_university_events, _launch_events, _workflow_events, _task_events, _contract_events]
