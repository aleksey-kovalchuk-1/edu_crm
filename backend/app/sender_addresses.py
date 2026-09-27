"""Sender address rules shared by selection, every send, and the confirmation link (spec 2026-09-27,
section 2)."""
import secrets
from datetime import timedelta

from sqlalchemy import select

from .email import EmailSendError, send_email
from .errors import AppError, ErrorCode
from .models import EmailSenderIdentity, utcnow
from .organization import organization_name
from .security import token_hash

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


CONFIRMATION_TTL = timedelta(hours=48)
RESEND_COOLDOWN_SECONDS = 60
INVALID_LINK = 'Ссылка недействительна или устарела'


def issue_confirmation(db, request, identity):
    """A new single-use link (replacing any previous one) mailed to the address itself, from the system
    sender. Returns (delivered, message), following the project's honesty rule for unconfigured mail."""
    settings = request.app.state.settings
    organization = organization_name(db)
    token = secrets.token_urlsafe(32)
    now = utcnow()
    identity.confirmation_token_hash = token_hash(token)
    identity.confirmation_expires_at = now + CONFIRMATION_TTL
    identity.confirmation_sent_at = now
    link = f'{settings.public_base_url}/confirm-sender?token={token}'
    # The whitespace after the link matters: the token must end where the URL does.
    body = (
        f'Этот адрес добавляют как адрес отправителя писем UniCRM («{identity.display_name}»).\n'
        f'Чтобы подтвердить, откройте ссылку и нажмите «Подтвердить»: {link}\n'
        'Ссылка действует 48 часов. Если вы не ожидали это письмо, просто проигнорируйте его.\n\n'
        f'{organization}'
    )
    sender = getattr(request.app.state, 'email_sender', None) or send_email
    try:
        sender(settings, identity.email_address, 'Подтвердите адрес отправителя UniCRM', body,
               from_address=settings.email_sender_address or None, from_name=organization)
    except EmailSendError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось отправить письмо подтверждения, попробуйте позже') from error
    if settings.email_provider_url or sender is not send_email:
        return True, f'Письмо подтверждения отправлено на {identity.email_address}.'
    return False, 'Почтовый провайдер не настроен: письмо подтверждения записано только в журнал сервера.'
