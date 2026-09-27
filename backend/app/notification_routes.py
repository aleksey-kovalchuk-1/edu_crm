"""The signed-in user's own notifications, preferences and pause (spec 2026-09-27-notifications, «API»).
Every list and count is filtered by what the user can see right now."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .auth import ALL_ROLES, ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import Notification, NotificationPreference, utcnow
from .notification_scheduler import FIRST_HOUR, user_zone
from .notifications import EVENT_TYPES, FOREVER, GROUPS, UNSCOPED_EVENTS, can_see, is_enabled, visible_notifications

router = APIRouter(prefix='/api/v1/notifications', tags=['Уведомления'])
any_role = require_roles(*ALL_ROLES, ROLE_SUPERADMIN)
PATHS = {'university': '/universities/{}', 'launch': '/interactions/{}', 'task': '/tasks/{}'}


class LinkOut(BaseModel):
    type: str
    id: int
    path: str


class NotificationOut(BaseModel):
    id: int
    event_type: str
    title: str
    body: str
    link: LinkOut | None
    created_at: datetime
    read_at: datetime | None


class CountOut(BaseModel):
    count: int


class EventPreferenceOut(BaseModel):
    key: str
    label: str
    enabled: bool
    default: bool


class GroupOut(BaseModel):
    key: str
    label: str
    events: list[EventPreferenceOut]


class PreferencesOut(BaseModel):
    groups: list[GroupOut]
    paused_until: datetime | None


class PreferencesIn(BaseModel):
    preferences: dict[str, bool]


class PauseIn(BaseModel):
    duration: Literal['1h', 'tomorrow', '1w', 'forever', 'off']


class PauseOut(BaseModel):
    paused_until: datetime | None


def _link_visible(db, user, row):
    # Rows already passed visible_notifications(); only removal notices can point at something now hidden.
    return row.event_type not in UNSCOPED_EVENTS or can_see(db, user, row.link_type, row.link_id, row.university_id)


def _out(row, link_visible):
    link = None
    if link_visible:
        # Contracts open on their university page: there is no «Договоры» navigation item.
        path = f'/universities/{row.university_id}' if row.link_type == 'contract' else PATHS[row.link_type].format(row.link_id)
        link = LinkOut(type=row.link_type, id=row.link_id, path=path)
    return NotificationOut(id=row.id, event_type=row.event_type, title=row.title, body=row.body, link=link,
                           created_at=row.created_at, read_at=row.read_at)


@router.get('', response_model=list[NotificationOut], summary='Мои уведомления')
def list_notifications(unread: bool = False, limit: int = Query(50, ge=1, le=100),
                       auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    query = select(Notification).where(Notification.user_id == auth.user.id, visible_notifications(auth.user))
    if unread:
        query = query.where(Notification.read_at.is_(None))
    rows = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    return [_out(row, _link_visible(db, auth.user, row)) for row in rows]


@router.get('/unread-count', response_model=CountOut, summary='Число непрочитанных уведомлений')
def unread_count(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    # Same filter as the list, so the badge and the panel always agree.
    return CountOut(count=db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == auth.user.id, Notification.read_at.is_(None), visible_notifications(auth.user))))


@router.post('/read-all', status_code=204, summary='Отметить все уведомления прочитанными')
def read_all(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == auth.user.id, Notification.read_at.is_(None))
               .values(read_at=utcnow()))
    db.commit()


@router.post('/{notification_id}/read', status_code=204, summary='Отметить уведомление прочитанным')
def read_one(notification_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != auth.user.id:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    if row.read_at is None:
        row.read_at = utcnow()
        db.commit()


def _preferences(db, user):
    groups = [GroupOut(key=key, label=label, events=[
        EventPreferenceOut(key=event_key, label=event.label, enabled=is_enabled(db, user.id, event_key), default=event.default)
        for event_key, event in EVENT_TYPES.items() if event.group == key
    ]) for key, label in GROUPS]
    return PreferencesOut(groups=groups, paused_until=user.notifications_paused_until)


@router.get('/preferences', response_model=PreferencesOut, summary='Мои настройки уведомлений')
def get_preferences(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    return _preferences(db, auth.user)


@router.put('/preferences', response_model=PreferencesOut, summary='Сохранить настройки уведомлений')
def set_preferences(data: PreferencesIn, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    unknown = sorted(set(data.preferences) - set(EVENT_TYPES))
    if unknown:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[
            {'field': f'preferences.{key}', 'message': 'Неизвестный тип уведомления', 'type': 'value_error'} for key in unknown])
    for key, enabled in data.preferences.items():
        db.merge(NotificationPreference(user_id=auth.user.id, event_type=key, enabled=enabled))
    db.commit()
    return _preferences(db, auth.user)


def pause_end(user, duration, now):
    if duration == 'off':
        return None
    if duration == 'forever':
        return FOREVER
    if duration == '1h':
        return now + timedelta(hours=1)
    if duration == '1w':
        return now + timedelta(weeks=1)
    zone = user_zone(user)  # 'tomorrow': 08:00 of the next day in the user's own time zone
    tomorrow = now.astimezone(zone).date() + timedelta(days=1)
    return datetime.combine(tomorrow, FIRST_HOUR, tzinfo=zone).astimezone(timezone.utc)


@router.put('/pause', response_model=PauseOut, summary='Приостановить уведомления')
def set_pause(data: PauseIn, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    auth.user.notifications_paused_until = pause_end(auth.user, data.duration, utcnow())
    db.commit()
    return PauseOut(paused_until=auth.user.notifications_paused_until)
