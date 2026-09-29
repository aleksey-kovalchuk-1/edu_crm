"""New Keycloak sign-ups waiting for a CRM role (owner decisions 2026-09-28/29: sign-up stays in Keycloak; the
superadmin grants access in «Пользователи и роли»). Runs every minute in the notifier.

As soon as an enabled account with an e-mail and no CRM role appears:
- every superadmin gets one bell notification (dedupe key per Keycloak account, so repeated passes add nothing);
- the administrator (ACCESS_CONTACT_EMAIL, else the organisation's e-mail) gets one e-mail about it.
Both say whether the applicant has confirmed their address yet.

The applicant gets the owner's acknowledgement e-mail once, but only after confirming their address: an unconfirmed
address may belong to someone else, so nothing is sent to it.

Each sent e-mail is recorded as an audit event (`registration.admin_notified`, `registration.acknowledged`); a failed
send leaves no record and is retried on the next pass. Without a real mail provider (log-only mode) nothing is sent
or recorded, so the e-mails go out once one is configured.
"""
import logging

from sqlalchemy import exists, select

from .audit import record_event
from .auth import ROLE_SUPERADMIN
from .email import EmailSendError
from .keycloak_admin import KeycloakAdminError
from .models import AuditEvent, OrganizationProfile, User
from .notifications import notify

logger = logging.getLogger(__name__)

CRM_ROLES = frozenset({'crm-user', 'crm-supervisor', 'crm-admin', 'crm-superadmin'})
ACK_SUBJECT = 'UniCRM: заявка на доступ получена'
ACK_EVENT = 'registration.acknowledged'
ADMIN_SUBJECT = 'UniCRM: новая заявка на доступ'
ADMIN_EVENT = 'registration.admin_notified'
PAGE = 200


def acknowledgement_text(contact_email: str) -> str:
    # The owner's wording (2026-09-28), word for word.
    return ('Администратор получил вашу регистрацию. В ближайшее время он ее рассмотрит. '
            f'Если вы уже долго ждете, напишите на почту Администратору: {contact_email}.')


def admin_alert_text(*, name, username, email, confirmed, crm_url) -> str:
    status = ('Адрес электронной почты подтверждён.' if confirmed
              else 'Заявитель ещё не подтвердил адрес электронной почты по ссылке из письма.')
    return (f'В UniCRM зарегистрировался новый пользователь и ждёт доступа.\n\n'
            f'Имя: {name}\nЛогин: {username}\nЭлектронная почта: {email}\n{status}\n\n'
            f'Выдать доступ: {crm_url}/settings/users (Настройки → Пользователи и роли → Заявки на доступ).')


def _waiting(keycloak_admin):
    accounts, first = [], 0
    while True:
        page = keycloak_admin.list_users(first=first, max_results=PAGE)
        accounts.extend(page)
        if len(page) < PAGE:
            break
        first += PAGE
    return [a for a in accounts if a.email and a.enabled and CRM_ROLES.isdisjoint(a.roles)]


def _contact(db, contact_email):
    return contact_email or db.scalar(select(OrganizationProfile.email)) or ''


def _already(db, action, account_id):
    return db.scalar(select(exists().where(
        AuditEvent.action == action, AuditEvent.entity_type == 'keycloak_user', AuditEvent.entity_id == account_id)))


def _send_once(db, send, action, account, to, subject, body, summary):
    """Sends unless already recorded; returns whether it sent now."""
    if _already(db, action, account.id):
        return False
    try:
        send(to, subject, body)
    except EmailSendError:
        logger.warning('%s: sending failed; retrying next pass', action)
        return False
    record_event(db, None, None, action, entity_type='keycloak_user', entity_id=account.id, summary=summary,
                 payload={'keycloak_id': account.id})
    db.commit()
    return True


def watch_registrations(session_factory, keycloak_admin, *, send, contact_email, email_configured, crm_url=''):
    """One pass; returns counts. `send(to, subject, body)` raises EmailSendError on failure."""
    result = {'pending': 0, 'notified': 0, 'admin_emailed': 0, 'acknowledged': 0}
    if not keycloak_admin.is_configured():
        return result
    try:
        waiting = _waiting(keycloak_admin)
    except KeycloakAdminError:
        logger.warning('sign-up check skipped: the sign-in service is unavailable')
        return result
    result['pending'] = len(waiting)
    with session_factory() as db:
        superadmins = db.scalars(select(User.id).where(
            User.is_active.is_(True), User.roles.any(ROLE_SUPERADMIN)).order_by(User.id)).all()
        contact = _contact(db, contact_email)
        for account in waiting:
            name = ' '.join(part for part in (account.first_name, account.last_name) if part) or account.username
            note = '' if account.email_verified else ' (адрес ещё не подтверждён)'
            for user_id in superadmins:
                if notify(db, user_id=user_id, event_type='registration_pending', title='Новая заявка на доступ',
                          body=f'{name} — {account.email}{note}', link_type='registration', link_id=0,
                          dedupe_key=f'registration_pending:{account.id}'):
                    result['notified'] += 1
            db.commit()

            if not email_configured or not contact:
                continue
            if _send_once(db, send, ADMIN_EVENT, account, contact, ADMIN_SUBJECT,
                          admin_alert_text(name=name, username=account.username, email=account.email,
                                           confirmed=account.email_verified, crm_url=crm_url),
                          f'Администратору отправлено письмо о новой заявке на доступ ({account.email})'):
                result['admin_emailed'] += 1
            if account.email_verified and _send_once(
                    db, send, ACK_EVENT, account, account.email, ACK_SUBJECT, acknowledgement_text(contact),
                    f'Отправлено подтверждение получения заявки на доступ ({account.email})'):
                result['acknowledged'] += 1
    return result
