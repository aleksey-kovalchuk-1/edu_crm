"""New Keycloak sign-ups waiting for a CRM role (owner decision 2026-09-28: sign-up stays in Keycloak; the
superadmin grants access in «Пользователи и роли»). Runs in each notifier pass.

A person counts once they have confirmed their e-mail and their account is enabled: an unconfirmed address may
belong to someone else, so nothing is sent to it. For each such person:
- every superadmin gets one bell notification (dedupe key per Keycloak account, so repeated passes add nothing);
- the person gets the owner's acknowledgement e-mail once. Success is recorded as the audit event
  `registration.acknowledged`; a failed send leaves no record and is retried on the next pass. Without a real mail
  provider (log-only mode) nothing is sent or recorded, so the e-mail goes out once one is configured.
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
PAGE = 200


def acknowledgement_text(contact_email: str) -> str:
    # The owner's wording (2026-09-28), word for word.
    return ('Администратор получил вашу регистрацию. В ближайшее время он ее рассмотрит. '
            f'Если вы уже долго ждете, напишите на почту Администратору: {contact_email}.')


def _waiting(keycloak_admin):
    accounts, first = [], 0
    while True:
        page = keycloak_admin.list_users(first=first, max_results=PAGE)
        accounts.extend(page)
        if len(page) < PAGE:
            break
        first += PAGE
    return [a for a in accounts if a.email and a.enabled and a.email_verified and CRM_ROLES.isdisjoint(a.roles)]


def _contact(db, contact_email):
    return contact_email or db.scalar(select(OrganizationProfile.email)) or ''


def watch_registrations(session_factory, keycloak_admin, *, send, contact_email, email_configured):
    """One pass; returns counts. `send(to, subject, body)` raises EmailSendError on failure."""
    result = {'pending': 0, 'notified': 0, 'acknowledged': 0}
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
            for user_id in superadmins:
                if notify(db, user_id=user_id, event_type='registration_pending', title='Новая заявка на доступ',
                          body=f'{name} — {account.email}', link_type='registration', link_id=0,
                          dedupe_key=f'registration_pending:{account.id}'):
                    result['notified'] += 1
            db.commit()

            if not email_configured or not contact:
                continue
            acknowledged = db.scalar(select(exists().where(
                AuditEvent.action == ACK_EVENT, AuditEvent.entity_type == 'keycloak_user',
                AuditEvent.entity_id == account.id)))
            if acknowledged:
                continue
            try:
                send(account.email, ACK_SUBJECT, acknowledgement_text(contact))
            except EmailSendError:
                logger.warning('acknowledgement to a new sign-up failed; retrying next pass')
                continue
            record_event(db, None, None, ACK_EVENT, entity_type='keycloak_user', entity_id=account.id,
                         summary=f'Отправлено подтверждение получения заявки на доступ ({account.email})',
                         payload={'keycloak_id': account.id})
            db.commit()
            result['acknowledged'] += 1
    return result
