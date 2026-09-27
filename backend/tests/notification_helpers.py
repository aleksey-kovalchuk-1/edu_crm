"""Shared setup for notification event tests: real users logged in through the fake Keycloak."""
from sqlalchemy import select

from app.models import Notification, NotificationPreference, User
from helpers import database, login


def sign_in(client, keycloak, role, subject, name):
    client.cookies.clear()
    client.headers.pop('X-CSRF-Token', None)
    return login(client, keycloak, roles=(role,), subject=subject, name=name, email=f'{subject}@x.test')['user']


def enable(database_url, user_id, *event_types):
    with database(database_url) as db:
        for event_type in event_types:
            db.merge(NotificationPreference(user_id=user_id, event_type=event_type, enabled=True))
        db.commit()


def disable(database_url, user_id, *event_types):
    with database(database_url) as db:
        for event_type in event_types:
            db.merge(NotificationPreference(user_id=user_id, event_type=event_type, enabled=False))
        db.commit()


def notifications(database_url, user_id=None, event_type=None):
    with database(database_url) as db:
        query = select(Notification).order_by(Notification.id)
        if user_id is not None:
            query = query.where(Notification.user_id == user_id)
        if event_type is not None:
            query = query.where(Notification.event_type == event_type)
        return [(n.user_id, n.event_type, n.link_type, n.link_id) for n in db.scalars(query)]


def ensure_user(database_url, subject, name, roles=('crm-user',)):
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == subject))
        if user is None:
            user = User(keycloak_sub=subject, email=f'{subject}@x.test', full_name=name, roles=list(roles))
            db.add(user)
            db.commit()
        return user.id
