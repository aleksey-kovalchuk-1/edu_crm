"""Browser login through Keycloak, server-side sessions, CSRF protection and role checks.

Design and rationale: docs/design/authentication.md (decisions D-104, D-118, D-124, D-125, D-133–D-135).
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import get_db
from .errors import AppError, ErrorCode
from .models import LoginState, User, UserSession, utcnow
from .oidc import OIDCError, OIDCUnavailable
from .security import new_token, pkce_pair, safe_next_path, token_hash, tokens_match

logger = logging.getLogger(__name__)

SESSION_COOKIE = 'edu_crm_session'
LOGIN_COOKIE = 'edu_crm_login'
LOGIN_COOKIE_PATH = '/api/v1/auth'
LOGIN_STATE_TTL = timedelta(minutes=10)
# Upper bound on unfinished logins across the system, so anonymous requests cannot grow the table without limit.
MAX_PENDING_LOGINS = 1000
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


def _is_live(session, user, now):
    return session is not None and user is not None and session.revoked_at is None and session.expires_at > now and user.is_active


def _callback_redirect(request, location):
    # Every callback outcome removes the one-time login cookie.
    response = RedirectResponse(location, status_code=302)
    response.delete_cookie(LOGIN_COOKIE, path=LOGIN_COOKIE_PATH, httponly=True, samesite='lax', secure=request.app.state.settings.cookie_secure)
    return response


def _login_error(request, code):
    # The browser is in the middle of a redirect, so failures return to the interface as a query parameter.
    return _callback_redirect(request, f'/?auth_error={code}')


@router.get('/login', summary='Начать вход через Keycloak', status_code=302, response_class=RedirectResponse)
def login(request: Request, next_path: str = Query('/', alias='next'), db: Session = Depends(get_db)):
    app_state = request.app.state
    now = utcnow()
    db.execute(delete(LoginState).where(LoginState.expires_at < now))
    if db.scalar(select(func.count()).select_from(LoginState)) >= MAX_PENDING_LOGINS:
        db.commit()
        raise AppError(ErrorCode.RATE_LIMITED, 'Слишком много незавершённых попыток входа, повторите позже')

    raw_state, nonce, browser_value = new_token(), new_token(), new_token()
    verifier, challenge = pkce_pair()
    db.add(LoginState(
        state_hash=token_hash(raw_state),
        nonce=nonce,
        code_verifier=verifier,
        next_path=safe_next_path(next_path),
        browser_hash=token_hash(browser_value),
        created_at=now,
        expires_at=now + LOGIN_STATE_TTL,
    ))
    db.commit()

    url = app_state.oidc.authorization_url(redirect_uri=app_state.settings.callback_url, state=raw_state, nonce=nonce, code_challenge=challenge)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        LOGIN_COOKIE, browser_value, max_age=int(LOGIN_STATE_TTL.total_seconds()), path=LOGIN_COOKIE_PATH,
        httponly=True, samesite='lax', secure=app_state.settings.cookie_secure,
    )
    return response


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
        return _login_error(request, 'LOGIN_CANCELLED' if error == 'access_denied' else 'LOGIN_FAILED')
    browser_value = request.cookies.get(LOGIN_COOKIE)
    if not code or not state:
        return _login_error(request, 'LOGIN_FAILED')
    if not browser_value:
        return _login_error(request, 'LOGIN_EXPIRED')

    # DELETE ... RETURNING consumes the state atomically, and only for the browser that started this login:
    # a replayed callback, or a callback link planted in another browser (login CSRF), finds nothing.
    pending = db.execute(
        delete(LoginState)
        .where(LoginState.state_hash == token_hash(state), LoginState.browser_hash == token_hash(browser_value))
        .returning(LoginState.nonce, LoginState.code_verifier, LoginState.next_path, LoginState.expires_at)
    ).first()
    db.commit()
    now = utcnow()
    if pending is None or pending.expires_at <= now:
        return _login_error(request, 'LOGIN_EXPIRED')

    try:
        tokens = app_state.oidc.exchange_code(code=code, redirect_uri=app_state.settings.callback_url, code_verifier=pending.code_verifier)
        identity = app_state.oidc.verify_id_token(tokens.id_token, nonce=pending.nonce)
    except OIDCError as exc:
        logger.warning('Login failed: %s', exc)
        return _login_error(request, 'LOGIN_FAILED')
    if not identity.roles:
        return _login_error(request, 'NO_ACCESS')

    # An upsert avoids a unique-constraint race when the same account logs in from two tabs at once.
    # Deactivated accounts are left untouched and get no session.
    upsert = insert(User).values(
        keycloak_sub=identity.subject, email=identity.email, full_name=identity.full_name,
        roles=list(identity.roles), is_active=True, created_at=now, last_login_at=now,
    )
    row = db.execute(
        upsert.on_conflict_do_update(
            index_elements=[User.keycloak_sub],
            set_={'email': identity.email, 'full_name': identity.full_name, 'roles': list(identity.roles), 'last_login_at': now},
            where=User.is_active.is_(True),
        ).returning(User.id)
    ).first()
    if row is None:
        db.rollback()
        return _login_error(request, 'NO_ACCESS')

    raw_session = new_token()
    ttl = timedelta(hours=app_state.settings.session_ttl_hours)
    db.add(UserSession(
        id=token_hash(raw_session),
        user_id=row.id,
        csrf_token=new_token(),
        refresh_token_encrypted=app_state.cipher.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
        created_at=now,
        expires_at=now + ttl,
        validated_at=now,
        ip=request.client.host if request.client else None,
        user_agent=(request.headers.get('user-agent') or '')[:300] or None,
    ))
    db.commit()

    response = _callback_redirect(request, pending.next_path)
    response.set_cookie(
        SESSION_COOKIE, raw_session, max_age=int(ttl.total_seconds()), path='/',
        httponly=True, samesite='lax', secure=app_state.settings.cookie_secure,
    )
    return response


def _authenticate(request, db, *, revalidate):
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

    if revalidate and (now - session.validated_at).total_seconds() >= request.app.state.settings.session_revalidate_seconds:
        session, user = _revalidate(request, db, session_id, now)
    if request.method in UNSAFE_METHODS:
        _check_csrf(request, session)
    return AuthContext(user=user, session=session)


def current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    return _authenticate(request, db, revalidate=True)


def logout_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    # Signing out must work even while Keycloak is unavailable, so it skips revalidation.
    return _authenticate(request, db, revalidate=False)


current_auth.authenticates = True
logout_auth.authenticates = True


def _revalidate(request, db, session_id, now):
    app_state = request.app.state
    # Lock the row and re-read it from the database (populate_existing): Keycloak rotates refresh tokens on use,
    # and a concurrent request may already have refreshed this session while we waited for the lock.
    session = db.scalar(
        select(UserSession).where(UserSession.id == session_id).with_for_update().execution_options(populate_existing=True)
    )
    user = db.scalar(select(User).where(User.id == session.user_id).execution_options(populate_existing=True)) if session is not None else None
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
        if not tokens.id_token:
            raise OIDCError('refresh response has no id_token, roles cannot be confirmed')
        identity = app_state.oidc.verify_id_token(tokens.id_token)
        if identity.subject != user.keycloak_sub:
            raise OIDCError('refreshed token belongs to another subject')
    except OIDCUnavailable as exc:
        # Nothing was decided about the user: keep the session and let the client retry later.
        logger.warning('Keycloak unavailable during session revalidation: %s', exc)
        db.rollback()
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Сервис входа временно недоступен, повторите попытку позже')
    except OIDCError as exc:
        logger.info('Session revoked after failed revalidation with Keycloak: %s', exc)
        session.revoked_at = now
        db.commit()
        raise AppError(ErrorCode.UNAUTHENTICATED)

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
        raise AppError(ErrorCode.CSRF_INVALID, 'Запрос отправлен с недоверенного сайта')
    if not tokens_match(session.csrf_token, request.headers.get('x-csrf-token')):
        raise AppError(ErrorCode.CSRF_INVALID)


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
def logout(request: Request, response: Response, auth: AuthContext = Depends(logout_auth), db: Session = Depends(get_db)):
    app_state = request.app.state
    settings = app_state.settings
    start_page = f'{settings.public_base_url}/'
    keycloak_logout_page = app_state.oidc.end_session_url(post_logout_redirect_uri=start_page)

    refresh_token = app_state.cipher.decrypt(auth.session.refresh_token_encrypted) if auth.session.refresh_token_encrypted else None
    logout_url = start_page
    if refresh_token is None:
        logout_url = keycloak_logout_page
    else:
        try:
            app_state.oidc.end_session(refresh_token)
        except OIDCUnavailable as exc:
            # The CRM session still ends; the Keycloak page lets the user end the single sign-on session too.
            logger.warning('Keycloak unavailable during logout: %s', exc)
            logout_url = keycloak_logout_page
        except OIDCError as exc:
            logger.info('Keycloak had already ended the session: %s', exc)

    auth.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='lax', secure=settings.cookie_secure)
    return LogoutResponse(logout_url=logout_url)
