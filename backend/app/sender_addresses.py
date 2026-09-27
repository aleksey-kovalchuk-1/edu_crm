"""Sender address rules shared by selection and every send (spec 2026-09-27, section 2)."""
from sqlalchemy import select

from .errors import AppError, ErrorCode
from .models import EmailSenderIdentity

SENDER_UNAVAILABLE = 'Выбранный адрес отправителя недоступен — выберите другой в профиле'


def is_usable(identity, user) -> bool:
    return (identity is not None and identity.is_active and identity.status == 'active'
            and identity.owner_user_id in (None, user.id))


def usable_sender(db, user, identity_id):
    """Fresh read right before use: a concurrent deactivation, rejection or ownership change must win
    over whatever this request loaded earlier."""
    identity = db.scalar(
        select(EmailSenderIdentity).where(EmailSenderIdentity.id == identity_id)
        .with_for_update(read=True).execution_options(populate_existing=True)
    )
    if not is_usable(identity, user):
        raise AppError(ErrorCode.CONFLICT, SENDER_UNAVAILABLE)
    return identity
