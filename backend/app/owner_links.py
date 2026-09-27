"""Interaction owner ↔ CRM user links (spec 2026-09-27, section 1.2).

`Launch.owner` stays free text typed by people; `Launch.owner_user_id` is set only when that text
matches exactly one ACTIVE user by normalized name. Plan assignment prefers the link, and a rename
rewrites `owner` on linked rows so report filters keep one value per person.
"""
from sqlalchemy import func, select, update

from .audit import record_event
from .models import Launch, User


def normalize_name(value: str) -> str:
    return ' '.join((value or '').split()).lower()


def normalized_column(column):
    return func.lower(func.regexp_replace(func.btrim(column), r'\s+', ' ', 'g'))


def match_owner_user(db, owner_text: str) -> int | None:
    wanted = normalize_name(owner_text)
    if not wanted:
        return None
    ids = db.scalars(
        select(User.id).where(User.is_active.is_(True), normalized_column(User.full_name) == wanted).limit(2)
    ).all()
    return ids[0] if len(ids) == 1 else None


def rename_user(db, request, user, *, first_name, last_name, full_name):
    """Writes the name fields; if full_name changed, rewrites `owner` on this user's linked
    interactions and records `user.renamed`. Returns the number of rewritten interactions. No commit."""
    previous = user.full_name
    user.first_name = first_name
    user.last_name = last_name
    user.full_name = full_name
    if previous == full_name:
        return 0
    updated = db.execute(update(Launch).where(Launch.owner_user_id == user.id).values(owner=full_name)).rowcount
    record_event(
        db, request, user, 'user.renamed', entity_type='user', entity_id=user.id,
        summary=f'Имя пользователя изменено: «{previous}» → «{full_name}»',
        payload={'from': previous, 'to': full_name, 'launches': updated},
    )
    return updated
