"""Browser login through Keycloak, server-side sessions, CSRF protection and role checks.

Design and rationale: docs/design/authentication.md (decisions D-104, D-118, D-124, D-125).
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_db
from .errors import AppError, ErrorCode
from .models import LoginState, User, UserSession, utcnow
from .oidc import OIDCError
from .security import new_token, pkce_pair, safe_next_path, token_hash, tokens_match

logger = logging.getLogger(__name__)

SESSION_COOKIE = 'edu_crm_session'
LOGIN_STATE_TTL = timedelta(minutes=10)
UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

ROLE_USER = 'crm-user'
ROLE_SUPERVISOR = 'crm-supervisor'
ROLE_ADMIN = 'crm-admin'
ALL_ROLES = (ROLE_USER, ROLE_SUPERVISOR, ROLE_ADMIN)

router = APIRouter(prefix='/api/v1/auth', tags=['Аутентификация'])


class CurrentUser(BaseModel):
    id: int
    email: str
    full_name: str
    roles: list[str]


class MeResponse(BaseModel):
    user: CurrentUser
    csrf_token: str


class LogoutResponse(BaseModel):
    logout_url: str


@dataclass
class AuthContext:
    user: User
    session: UserSession


def _login_error(code):
    # The browser is in the middle of a redirect, so failures return to the interface as a query parameter.
    return RedirectResponse(f'/?auth_error={code}', status_code=302)


def _is_live(session, user, now):
    return session is not None and user is not None and session.revoked_at is None and session.expires_at > now and user.is_active


@router.get('/login', summary='Начать вход через Keycloak', status_code=302, response_class=RedirectResponse)
def login(request: Request, next_path: str = Query('/', alias='next'), db: Session = Depends(get_db)):
    app_state = request.app.state
    raw_state, nonce = new_token(), new_token()
    verifier, challenge = pkce_pair()
    now = utcnow()
    db.execute(delete(LoginState).where(LoginState.expires_at < now))
    db.add(LoginState(
        state_hash=token_hash(raw_state),
        nonce=nonce,
        code_verifier=verifier,
        next_path=safe_next_path(next_path),
        created_at=now,
        expires_at=now + LOGIN_STATE_TTL,
    ))
    db.commit()
    url = app_state.oidc.authorization_url(
        redirect_uri=app_state.settings.callback_url, state=raw_state, nonce=nonce, code_challenge=challenge,
    )
    return RedirectResponse(url, status_code=302)


@router.get('/callback', summary='Завершить вход (адрес возврата из Keycloak)', status_code=302, response_class=RedirectResponse)
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    app_state = request.app.state
    if error:
        return _login_error('LOGIN_CANCELLED' if error == 'access_denied' else 'LOGIN_FAILED')
    if not code or not state:
        return _login_error('LOGIN_FAILED')

    # Deleting with RETURNING consumes the state atomically, so a replayed or concurrent callback cannot reuse it.
    pending = db.execute(
        delete(LoginState)
        .where(LoginState.state_hash == token_hash(state))
        .returning(LoginState.nonce, LoginState.code_verifier, LoginState.next_path, LoginState.expires_at)
    ).first()
    db.commit()
    now = utcnow()
    if pending is None or pending.expires_at <= now:
        return _login_error('LOGIN_EXPIRED')

    try:
        tokens = app_state.oidc.exchange_code(code=code, redirect_uri=app_state.settings.callback_url, code_verifier=pending.code_verifier)
        identity = app_state.oidc.verify_id_token(tokens.id_token, nonce=pending.nonce)
    except OIDCError as exc:
        logger.warning('Login failed: %s', exc)
        return _login_error('LOGIN_FAILED')
    if not identity.roles:
        return _login_error('NO_ACCESS')

    user = db.scalar(select(User).where(User.keycloak_sub == identity.subject))
    if user is None:
        user = User(keycloak_sub=identity.subject, is_active=True)
        db.add(user)
    elif not user.is_active:
        return _login_error('NO_ACCESS')
    user.email = identity.email
    user.full_name = identity.full_name
    user.roles = list(identity.roles)
    user.last_login_at = now
    db.flush()

    raw_session = new_token()
    ttl = timedelta(hours=app_state.settings.session_ttl_hours)
    db.add(UserSession(
        id=token_hash(raw_session),
        user_id=user.id,
        csrf_token=new_token(),
        refresh_token_encrypted=app_state.cipher.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        created_at=now,
        expires_at=now + ttl,
        validated_at=now,
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get('user-agent') or '')[:300] or None,
    ))
    db.commit()

    response = RedirectResponse(pending.next_path, status_code=302)
    response.set_cookie(
        SESSION_COOKIE, raw_session, max_age=int(ttl.total_seconds()), path='/',
        httponly=True, samesite='lax', secure=app_state.settings.cookie_secure,
    )
    return response


def current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    raw_session = request.cookies.get(SESSION_COOKIE)
    if not raw_session:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    session_id = token_hash(raw_session)
    row = db.execute(
        select(UserSession, User).join(User, User.id == UserSession.user_id).where(UserSession.id == session_id)
    ).first()
    now = utcnow()
    if row is None or not _is_live(row.UserSession, row.User, now):
        raise AppError(ErrorCode.UNAUTHENTICATED)
    session, user = row.UserSession, row.User

    if (now - session.validated_at).total_seconds() >= request.app.state.settings.session_revalidate_seconds:
        session, user = _revalidate(request, db, session_id, now)
    if request.method in UNSAFE_METHODS:
        _check_csrf(request, session)
    return AuthContext(user=user, session=session)


def _revalidate(request, db, session_id, now):
    app_state = request.app.state
    # Lock the row: Keycloak rotates refresh tokens on use, so concurrent requests must not refresh twice.
    session = db.scalar(select(UserSession).where(UserSession.id == session_id).with_for_update())
    user = db.get(User, session.user_id) if session is not None else None
    if not _is_live(session, user, now):
        db.rollback()
        raise AppError(ErrorCode.UNAUTHENTICATED)
    if (now - session.validated_at).total_seconds() < app_state.settings.session_revalidate_seconds:
        db.commit()
        return session, user

    refresh_token = app_state.cipher.decrypt(session.refresh_token_encrypted) if session.refresh_token_encrypted else None
    try:
        if refresh_token is None:
            raise OIDCError('session has no usable refresh token')
        tokens = app_state.oidc.refresh(refresh_token)
        identity = app_state.oidc.verify_id_token(tokens.id_token) if tokens.id_token else None
        if identity is not None and identity.subject != user.keycloak_sub:
            raise OIDCError('refreshed token belongs to another subject')
    except OIDCError as exc:
        logger.info('Session revoked after failed revalidation with Keycloak: %s', exc)
        session.revoked_at = now
        db.commit()
        raise AppError(ErrorCode.UNAUTHENTICATED)

    if identity is not None:
        user.email = identity.email
        user.full_name = identity.full_name
        user.roles = list(identity.roles)
    if tokens.refresh_token:
        session.refresh_token_encrypted = app_state.cipher.encrypt(tokens.refresh_token)
    session.validated_at = now
    if not user.roles:
        session.revoked_at = now
    db.commit()
    if session.revoked_at is not None:
        raise AppError(ErrorCode.UNAUTHENTICATED)
    return session, user


def _check_csrf(request, session):
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') not in request.app.state.settings.trusted_origins:
        raise AppError(ErrorCode.FORBIDDEN, 'Запрос отправлен с недоверенного сайта')
    if not tokens_match(session.csrf_token, request.headers.get('x-csrf-token')):
        raise AppError(ErrorCode.FORBIDDEN, 'Отсутствует или неверен CSRF-токен; обновите страницу')


def require_roles(*roles):
    allowed = frozenset(roles)

    def dependency(auth: AuthContext = Depends(current_auth)) -> AuthContext:
        if allowed.isdisjoint(auth.user.roles):
            raise AppError(ErrorCode.FORBIDDEN)
        return auth

    dependency.allowed_roles = allowed
    return dependency


@router.get('/me', response_model=MeResponse, summary='Текущий пользователь и CSRF-токен')
def me(auth: AuthContext = Depends(current_auth)):
    return MeResponse(
        user=CurrentUser(id=auth.user.id, email=auth.user.email, full_name=auth.user.full_name, roles=sorted(auth.user.roles)),
        csrf_token=auth.session.csrf_token,
    )


@router.post('/logout', response_model=LogoutResponse, summary='Выйти из CRM и Keycloak')
def logout(request: Request, response: Response, auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    auth.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax', secure=settings.cookie_secure)
    return LogoutResponse(logout_url=request.app.state.oidc.end_session_url(post_logout_redirect_uri=f'{settings.public_base_url}/'))
