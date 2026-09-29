"""Date-based notifications (spec 2026-09-27-notifications, «Планировщик»): tasks due today, overdue tasks,
and licences expiring in 30 or 7 days. Runs as the `notifier` Compose service every 15 minutes.

"Today" is each user's own day in their time zone, and nothing fires before 08:00 local time. Every
notification carries a dedupe key that includes the date it is about, so repeated runs add nothing while a
moved deadline or a renewed licence notifies again.
"""
import argparse
import logging
import time
from datetime import datetime, time as clock, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import sessionmaker

import httpx

from .email import email_configured, send_email
from .keycloak_admin import KeycloakAdminClient
from .models import Contract, Task, TaskMember, UniversityManager, User
from .notifications import notify
from .registration_watch import watch_registrations

logger = logging.getLogger(__name__)
INTERVAL_SECONDS = 15 * 60
FIRST_HOUR = clock(8, 0)
DEFAULT_ZONE = ZoneInfo('Europe/Moscow')
CLOSED = ('completed', 'cancelled')
def licence_warning(days_left):
    """A window, not an exact day: a contract added with 20 days left, or a day the notifier was down, still
    warns. The dedupe key (which includes valid_until) keeps each warning to once per licence period."""
    if 0 <= days_left <= 7:
        return 'license_expires_7'
    if 7 < days_left <= 30:
        return 'license_expires_30'
    return None


def user_zone(user):
    try:
        return ZoneInfo(user.timezone or 'Europe/Moscow')
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_ZONE


def _task_notifications(db, user, today, now):
    created = 0
    tasks = db.scalars(
        select(Task).join(TaskMember, TaskMember.task_id == Task.id)
        .where(TaskMember.user_id == user.id, TaskMember.role.in_(('assignee', 'participant')),
               Task.deadline.isnot(None), Task.deadline <= today, Task.status.notin_(CLOSED), Task.archived_at.is_(None))
        .distinct()
    ).all()
    for task in tasks:
        due_today = task.deadline == today
        event_type = 'task_due_today' if due_today else 'task_overdue'
        created += notify(
            db, user_id=user.id, event_type=event_type,
            title='Срок вашей задачи наступает сегодня' if due_today else 'Ваша задача просрочена',
            body=f'{task.title} · срок {task.deadline:%d.%m.%Y}', link_type='task', link_id=task.id,
            university_id=task.university_id, dedupe_key=f'{event_type}:{task.id}:{task.deadline.isoformat()}', now=now)
    return created


def _licence_notifications(db, user, today, now):
    created = 0
    contracts = db.scalars(
        select(Contract).where(Contract.valid_until.isnot(None), or_(
            Contract.manager_user_id == user.id,
            Contract.university_id.in_(select(UniversityManager.university_id).where(UniversityManager.user_id == user.id)),
        ))
    ).all()
    for contract in contracts:
        days = (contract.valid_until - today).days
        event_type = licence_warning(days)
        if event_type is None:
            continue
        created += notify(
            db, user_id=user.id, event_type=event_type,
            title='Лицензия истекает сегодня' if days == 0 else f'Лицензия истекает через {days} дн.',
            body=f'Договор {contract.contract_number} · до {contract.valid_until:%d.%m.%Y}', link_type='contract',
            link_id=contract.id, university_id=contract.university_id,
            dedupe_key=f'{event_type}:{contract.id}:{contract.valid_until.isoformat()}', now=now)
    return created


def run_once(session_factory, now=None):
    """One pass over every active user; returns how many notifications were created."""
    now = now or datetime.now(timezone.utc)
    created = 0
    with session_factory() as db:
        for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id)).all():
            local = now.astimezone(user_zone(user))
            if local.time() < FIRST_HOUR:
                continue
            created += _task_notifications(db, user, local.date(), now)
            created += _licence_notifications(db, user, local.date(), now)
        db.commit()
    return created


def registration_pass(session_factory, settings, keycloak_admin, sender=send_email):
    """New Keycloak sign-ups: bell notifications for superadmins and one acknowledgement e-mail each
    (app/registration_watch.py)."""
    return watch_registrations(
        session_factory, keycloak_admin, send=lambda to, subject, body: sender(settings, to, subject, body),
        contact_email=settings.access_contact_email, email_configured=email_configured(settings))


def main():
    from .settings import load_settings

    parser = argparse.ArgumentParser(description='Create date-based in-app notifications')
    parser.add_argument('--once', action='store_true', help='run a single pass and exit')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    settings = load_settings()
    session_factory = sessionmaker(bind=create_engine(settings.database_url, pool_pre_ping=True))
    keycloak_admin = KeycloakAdminClient(
        base_url=settings.keycloak_admin_base_url, client_id=settings.keycloak_admin_client_id,
        client_secret=settings.keycloak_admin_client_secret, http_client=httpx.Client(timeout=10),
    )
    while True:
        try:
            logger.info('notification scheduler pass created %d notification(s)', run_once(session_factory))
        except Exception:  # keep the service alive; the next pass retries
            logger.exception('notification scheduler pass failed')
        try:
            logger.info('sign-up check: %s', registration_pass(session_factory, settings, keycloak_admin))
        except Exception:
            logger.exception('sign-up check failed')
        if args.once:
            return
        time.sleep(INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
