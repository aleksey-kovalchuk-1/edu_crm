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


def install(session_factory):
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

HANDLERS = [_university_events, _launch_events, _workflow_events]
