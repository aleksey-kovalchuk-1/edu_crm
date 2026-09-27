"""Interaction owner ↔ CRM user links (spec 2026-09-27, section 1.2).

`Launch.owner` stays free text typed by people; `Launch.owner_user_id` is set only when that text
matches exactly one ACTIVE user by normalized name. Plan assignment prefers the link, and a rename
rewrites `owner` on linked rows so report filters keep one value per person.
"""
from sqlalchemy import func, select

from .models import User


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
