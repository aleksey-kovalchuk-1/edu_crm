"""In-app notifications (spec 2026-09-27-notifications): the event catalogue and the single place a
notification is created, with every rule that decides whether one is created at all."""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert

from .catalog_routes import university_scope
from .auth import ROLE_SUPERADMIN
from .models import Notification, NotificationPreference, Task, University, User, utcnow
from .task_policy import visible_tasks_query

# "Until turned off": far enough to never expire, and a plain timestamp (no 'infinity' special value).
FOREVER = datetime(9999, 12, 31, tzinfo=timezone.utc)

GROUPS = [
    ('universities', 'Вузы'),
    ('launches', 'Взаимодействия с вузами'),
    ('tasks', 'Задачи'),
    ('contracts', 'Договоры и лицензии'),
    # Superadmin only (SUPERADMIN_GROUPS): the sign-up queue in «Пользователи и роли».
    ('access', 'Доступ к CRM'),
]
SUPERADMIN_GROUPS = frozenset({'access'})


@dataclass(frozen=True)
class EventType:
    group: str
    label: str
    default: bool


EVENT_TYPES = {
    'university_assigned': EventType('universities', 'Вас назначили ответственным за вуз', True),
    'university_unassigned': EventType('universities', 'Вас сняли с ответственности за вуз', True),
    'university_contacts_changed': EventType('universities', 'Изменили контакты закреплённого за вами вуза', False),
    'launch_stage_changed': EventType('launches', 'Изменили этап взаимодействия по вашему вузу', False),
    'launch_comment_or_file': EventType('launches', 'Добавили комментарий или файл к взаимодействию по вашему вузу', False),
    'launch_completed': EventType('launches', 'Завершили взаимодействие по вашему вузу', False),
    'workflow_stages_changed': EventType('launches', 'Изменили этапы процесса, который используется в ваших взаимодействиях', False),
    'task_assigned': EventType('tasks', 'Вас назначили исполнителем или соисполнителем задачи', True),
    'task_unassigned': EventType('tasks', 'Вас убрали из исполнителей задачи', True),
    'task_deadline_changed': EventType('tasks', 'Изменили срок вашей задачи', True),
    'task_due_today': EventType('tasks', 'Срок вашей задачи наступает сегодня', True),
    'task_overdue': EventType('tasks', 'Ваша задача просрочена', True),
    'task_commented': EventType('tasks', 'Добавили комментарий к вашей задаче', True),
    'task_submitted_for_approval': EventType('tasks', 'Вашу задачу отправили на согласование', True),
    'task_review_decided': EventType('tasks', 'Вашу задачу согласовали или вернули на доработку', True),
    'task_closed': EventType('tasks', 'Задачу, в которой вы участвуете, завершили или отменили', True),
    'contract_signed': EventType('contracts', 'Подписали договор по вашему вузу', False),
    'contract_transfer_changed': EventType('contracts', 'Изменили статус передачи лицензий или материалов', False),
    'license_expires_30': EventType('contracts', 'Срок действия лицензии по вашему вузу истекает через 30 дней', False),
    'license_expires_7': EventType('contracts', 'Срок действия лицензии по вашему вузу истекает через 7 дней', False),
    'registration_pending': EventType('access', 'Новая заявка на доступ', True),
}

# Links for contracts point at the university page: there is no «Договоры» navigation item.
# 'registration' points at the sign-up queue (/settings/users); its link_id is always 0.
LINK_TYPES = ('university', 'launch', 'task', 'contract', 'registration')
# Sent to someone who is losing access: created without the visibility check and listed without a link
# once the record is no longer visible (the text only names what the person already knew).
UNSCOPED_EVENTS = frozenset({'university_unassigned', 'task_unassigned'})


def is_enabled(db, user_id, event_type) -> bool:
    stored = db.scalar(select(NotificationPreference.enabled).where(
        NotificationPreference.user_id == user_id, NotificationPreference.event_type == event_type))
    return EVENT_TYPES[event_type].default if stored is None else stored


def is_paused(user, now=None) -> bool:
    return user.notifications_paused_until is not None and user.notifications_paused_until > (now or utcnow())


def can_see(db, user, link_type, link_id, university_id) -> bool:
    """Checked in the database, so rows added earlier in this transaction (new members, new managers) count."""
    if link_type == 'registration':
        return ROLE_SUPERADMIN in user.roles
    if link_type == 'task':
        return bool(db.scalar(select(exists().where(Task.id == link_id, visible_tasks_query(user)))))
    if university_id is None:
        return False
    return bool(db.scalar(select(exists().where(University.id == university_id, university_scope(University.id, user)))))


def visible_notifications(user):
    """SQL filter: notifications about records `user` can see now, plus the removal notices (UNSCOPED_EVENTS).
    One query for any number of rows, so the list and the unread count agree and stay cheap to poll."""
    task_visible = exists().where(Task.id == Notification.link_id, visible_tasks_query(user))
    university_visible = exists().where(University.id == Notification.university_id, university_scope(University.id, user))
    clauses = [
        Notification.event_type.in_(UNSCOPED_EVENTS),
        and_(Notification.link_type == 'task', task_visible),
        and_(Notification.link_type != 'task', university_visible),
    ]
    if ROLE_SUPERADMIN in user.roles:
        clauses.append(Notification.link_type == 'registration')
    return or_(*clauses)


def notify(db, *, user_id, event_type, title, body, link_type, link_id, university_id=None, actor_user_id=None,
           dedupe_key=None, now=None) -> bool:
    """Creates one notification unless a rule says no. Returns whether one was created."""
    assert event_type in EVENT_TYPES and link_type in LINK_TYPES
    if user_id is None or user_id == actor_user_id:
        return False
    sent = db.info.setdefault('notified', set())
    marker = (user_id, event_type, link_type, link_id)
    if marker in sent:
        return False  # one action, one notification per recipient and entity
    user = db.get(User, user_id)
    if user is None or not user.is_active or is_paused(user, now):
        return False
    if not is_enabled(db, user_id, event_type):
        return False
    if event_type not in UNSCOPED_EVENTS and not can_see(db, user, link_type, link_id, university_id):
        return False
    values = dict(user_id=user_id, event_type=event_type, title=title[:200], body=body[:500], link_type=link_type,
                  link_id=link_id, university_id=university_id, actor_user_id=actor_user_id, dedupe_key=dedupe_key,
                  created_at=now or utcnow())
    if dedupe_key is None:
        db.add(Notification(**values))
    else:
        inserted = db.execute(
            insert(Notification).values(**values)
            .on_conflict_do_nothing(index_elements=['user_id', 'dedupe_key'], index_where=Notification.dedupe_key.isnot(None))
            .returning(Notification.id)
        ).first()
        if inserted is None:
            return False
    sent.add(marker)
    return True
