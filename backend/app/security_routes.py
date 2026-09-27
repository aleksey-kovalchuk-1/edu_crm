"""Настройки → Безопасность (spec 2026-09-27-security-settings): the signed-in user's own CRM sessions with
safe termination (also ending the Keycloak session), login history (CRM sign-ins + Keycloak events when
event storage is enabled), and the effective Keycloak password policy. No tokens or session keys leave here."""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .keycloak_admin import KeycloakAdminError, KeycloakAdminForbidden, KeycloakAdminUnavailable
from .models import UserSession, utcnow
from .password_policy import describe_policy

router = APIRouter(prefix='/api/v1/security', tags=['Безопасность'])
any_role = require_roles(*ALL_ROLES, ROLE_SUPERADMIN)
HISTORY_DAYS = 30
HISTORY_LIMIT = 50
KEYCLOAK_SELF_EXPIRY = 'Сеанс Keycloak завершится сам после 30 минут бездействия.'
EVENT_LABELS = {'LOGIN': 'Вход', 'LOGIN_ERROR': 'Неудачная попытка входа', 'LOGOUT': 'Выход',
                'UPDATE_PASSWORD': 'Смена пароля'}
BROWSERS = [('Edg/', 'Edge'), ('YaBrowser', 'Яндекс Браузер'), ('OPR/', 'Opera'), ('Firefox/', 'Firefox'),
            ('Chrome/', 'Chrome'), ('Safari/', 'Safari')]
SYSTEMS = [('Windows', 'Windows'), ('Android', 'Android'), ('iPhone', 'iOS'), ('iPad', 'iOS'),
           ('Mac OS X', 'macOS'), ('Linux', 'Linux')]


def public_id(session_id: str) -> str:
    """Non-reversible handle for a session; the real key (a hash of the cookie) never leaves the server."""
    return hashlib.sha256(f'public:{session_id}'.encode()).hexdigest()[:16]


def describe_device(user_agent: str | None) -> str:
    ua = user_agent or ''
    browser = next((name for marker, name in BROWSERS if marker in ua), None)
    system = next((name for marker, name in SYSTEMS if marker in ua), None)
    parts = [p for p in (browser, system) if p]
    return ' · '.join(parts) if parts else 'Неизвестное устройство'


class SessionOut(BaseModel):
    id: str
    device: str
    ip: str | None
    created_at: datetime
    last_active_at: datetime
    current: bool


class TerminateOut(BaseModel):
    keycloak_ended: bool
    message: str


class TerminateOthersOut(BaseModel):
    count: int
    keycloak_all_ended: bool
    message: str


def _live_sessions(db, user_id, now):
    return db.scalars(select(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now,
    ).order_by(UserSession.validated_at.desc())).all()


@router.get('/sessions', response_model=list[SessionOut], summary='Мои активные сеансы')
def list_sessions(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    return [SessionOut(id=public_id(s.id), device=describe_device(s.user_agent), ip=s.ip, created_at=s.created_at,
                       last_active_at=s.validated_at, current=s.id == auth.session.id)
            for s in _live_sessions(db, auth.user.id, utcnow())]


ENDED, SHARED, NOT_ENDED = 'ended', 'shared', 'not_ended'
MESSAGES = {
    ENDED: 'Сеанс завершён.',
    SHARED: 'Сеанс в CRM завершён. Вход в Keycloak общий с этим устройством и остаётся активным.',
    NOT_ENDED: f'Сеанс в CRM завершён. {KEYCLOAK_SELF_EXPIRY}',
}


def _end(request, auth, session, now, *, keycloak_down=False):
    """Revokes the CRM session and, when possible, its Keycloak session. Returns ENDED, SHARED (same
    Keycloak session as this device: left alone) or NOT_ENDED; raises nothing."""
    session.revoked_at = now
    sid = session.keycloak_session_id
    if sid and sid == auth.session.keycloak_session_id:
        return SHARED
    keycloak_admin = request.app.state.keycloak_admin
    if not sid or keycloak_down or not keycloak_admin.is_configured():
        return NOT_ENDED
    keycloak_admin.delete_session(sid)
    return ENDED


def _end_quietly(request, auth, session, now, *, keycloak_down=False):
    try:
        return _end(request, auth, session, now, keycloak_down=keycloak_down), False
    except KeycloakAdminUnavailable:
        return NOT_ENDED, True
    except KeycloakAdminError:
        return NOT_ENDED, False


@router.delete('/sessions/{session_public_id}', response_model=TerminateOut, summary='Завершить сеанс')
def terminate_session(session_public_id: str, request: Request, auth: AuthContext = Depends(any_role),
                      db: Session = Depends(get_db)):
    now = utcnow()
    session = next((s for s in _live_sessions(db, auth.user.id, now) if public_id(s.id) == session_public_id), None)
    if session is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    if session.id == auth.session.id:
        raise AppError(ErrorCode.CONFLICT, 'Для текущего устройства используйте «Выйти»')
    result, _ = _end_quietly(request, auth, session, now)
    record_event(db, request, auth.user, 'security.session_terminate', entity_type='user', entity_id=auth.user.id,
                 summary='Завершён сеанс на другом устройстве', payload={'keycloak_ended': result == ENDED})
    db.commit()
    return TerminateOut(keycloak_ended=result == ENDED, message=MESSAGES[result])


@router.post('/sessions/terminate-others', response_model=TerminateOthersOut, summary='Завершить все остальные сеансы')
def terminate_others(request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    now = utcnow()
    others = [s for s in _live_sessions(db, auth.user.id, now) if s.id != auth.session.id]
    results, keycloak_down = [], False
    for session in others:
        # After the first connection failure, stop calling Keycloak: a hanging Keycloak must not stretch
        # this request past the proxy timeout while the CRM sessions are already ended.
        result, down = _end_quietly(request, auth, session, now, keycloak_down=keycloak_down)
        keycloak_down = keycloak_down or down
        results.append(result)
    all_ended = all(r != NOT_ENDED for r in results)
    record_event(db, request, auth.user, 'security.sessions_terminate_others', entity_type='user', entity_id=auth.user.id,
                 summary=f'Завершены остальные сеансы ({len(others)})', payload={'count': len(others)})
    db.commit()
    message = 'Все остальные сеансы завершены.' if all_ended else f'Сеансы в CRM завершены. {KEYCLOAK_SELF_EXPIRY}'
    return TerminateOthersOut(count=len(others), keycloak_all_ended=all_ended, message=message)


class CrmLoginOut(BaseModel):
    at: datetime
    device: str
    ip: str | None
    state: str  # active | ended | expired


class KeycloakEventOut(BaseModel):
    at: datetime
    type: str
    label: str
    ip: str | None
    error: str | None


class KeycloakHistoryOut(BaseModel):
    available: bool
    reason: str | None  # not_configured | disabled | unavailable
    events: list[KeycloakEventOut]


class LoginHistoryOut(BaseModel):
    crm: list[CrmLoginOut]
    keycloak: KeycloakHistoryOut


def _keycloak_history(request, user):
    keycloak_admin = request.app.state.keycloak_admin
    if not keycloak_admin.is_configured():
        return KeycloakHistoryOut(available=False, reason='not_configured', events=[])
    try:
        if not keycloak_admin.get_realm_security()['events_enabled']:
            return KeycloakHistoryOut(available=False, reason='disabled', events=[])
        rows = keycloak_admin.list_user_events(user.keycloak_sub, max_results=HISTORY_LIMIT)
    except KeycloakAdminForbidden:
        return KeycloakHistoryOut(available=False, reason='disabled', events=[])  # view-events not granted yet
    except KeycloakAdminError:
        return KeycloakHistoryOut(available=False, reason='unavailable', events=[])
    events = [KeycloakEventOut(at=datetime.fromtimestamp(row['time'] / 1000, tz=timezone.utc), type=row['type'],
                               label=EVENT_LABELS.get(row['type'], row['type']), ip=row.get('ipAddress'),
                               error=row.get('error')) for row in rows if 'time' in row and 'type' in row]
    return KeycloakHistoryOut(available=True, reason=None, events=sorted(events, key=lambda e: e.at, reverse=True))


@router.get('/login-history', response_model=LoginHistoryOut, summary='История моих входов')
def login_history(request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    now = utcnow()
    sessions = db.scalars(select(UserSession).where(
        UserSession.user_id == auth.user.id, UserSession.created_at >= now - timedelta(days=HISTORY_DAYS),
    ).order_by(UserSession.created_at.desc()).limit(HISTORY_LIMIT)).all()
    crm = [CrmLoginOut(at=s.created_at, device=describe_device(s.user_agent), ip=s.ip,
                       state='ended' if s.revoked_at else ('expired' if s.expires_at <= now else 'active'))
           for s in sessions]
    return LoginHistoryOut(crm=crm, keycloak=_keycloak_history(request, auth.user))


class PasswordPolicyOut(BaseModel):
    available: bool
    rules: list[str]
    brute_force: str | None
    change_password_url: str
    admin_console_url: str | None


@router.get('/password-policy', response_model=PasswordPolicyOut, summary='Действующая парольная политика')
def password_policy(request: Request, auth: AuthContext = Depends(any_role)):
    issuer = request.app.state.settings.oidc_issuer.rstrip('/')
    change_url = f'{issuer}/account/account-security/signing-in'
    is_admin = not {ROLE_ADMIN, ROLE_SUPERADMIN}.isdisjoint(auth.user.roles)
    admin_url = f"{issuer.split('/realms/')[0]}/admin/master/console/#/edu-crm/authentication/policies" if is_admin else None
    keycloak_admin = request.app.state.keycloak_admin
    try:
        info = keycloak_admin.get_realm_security() if keycloak_admin.is_configured() else None
    except KeycloakAdminError:
        info = None
    if info is None:
        return PasswordPolicyOut(available=False, rules=[], brute_force=None, change_password_url=change_url,
                                 admin_console_url=admin_url)
    brute = (f"После {info['failure_factor']} неудачных попыток вход временно блокируется"
             if info['brute_force_protected'] and info['failure_factor'] else None)
    return PasswordPolicyOut(available=True, rules=describe_policy(info['password_policy']), brute_force=brute,
                             change_password_url=change_url, admin_console_url=admin_url)
