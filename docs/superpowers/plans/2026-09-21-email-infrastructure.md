# Email Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the backend a real, honest outgoing-email capability — mirroring the existing SMS abstraction exactly (logging-only by default, settings-gated real provider, fails closed) — plus an admin-managed catalog of sender identities users can pick from for university correspondence, and a safe test-send-to-self endpoint. No real SMTP/API credentials exist in this environment, matching the SMS module's own documented situation.

**Architecture:** `backend/app/email.py` mirrors `backend/app/sms.py` line-for-line in structure: `_log_sender`/`_http_sender`/`send_email(settings, to, subject, body)`, injectable via `create_app(..., email_sender=None)` exactly like `sms_sender` already is, so tests substitute a fake the same way. A new `EmailSenderIdentity` table is the catalog of "from" addresses a user may send university correspondence as — every row in it is inherently admin-approved, since only `crm-supervisor`/`crm-admin` can create one (no self-service "verify my own mailbox" flow is built — that would need its own confirmation-loop subsystem nothing in the spec asked for, and admin-managed is the correct minimal reading of "administrator-approved"). `User.email_sender_identity_id` is nullable — no sender selected is a normal, valid state, and the profile UI (a separate, later plan) is what lets a user pick one.

**Tech Stack:** FastAPI + httpx (backend/app/email.py, mirroring backend/app/sms.py's exact style), SQLAlchemy + Alembic (new table + column).

**Spec:** No separate spec doc — scoped in conversation on 2026-09-21 (the full 7-section "Настройки" request, this project's slice 3a of 9 total, split from "Личный профиль" per the owner's explicit instruction to keep infrastructure/security/email/scheduler changes clearly separated from feature UI work).

## Global Constraints

- Never expose mail credentials in the browser or claim sending works when no provider is configured — matches `sms.py`'s existing "logging-only, transparent" behavior exactly; the test-send endpoint (Task 3) must say plainly when a send was only logged, not actually delivered.
- No self-service "verify my own external mailbox" flow — sender identities are an admin-managed catalog only. A regular user can select among already-approved identities, never create or approve their own.
- Do not build a dedicated admin UI for managing sender identities in this plan — backend API only (list/create/deactivate), reachable by `crm-supervisor`/`crm-admin` today via the API directly; a UI for this can be added later (e.g. as part of Организация) without needing to revisit this plan's endpoints.
- Do not touch `backend/app/sms.py`, `backend/app/profile_routes.py`, or anything phone-verification-related — this plan is additive, new files only, except where noted (`main.py`, `settings.py`).
- Do not push or merge; local commits only.

---

### Task 1: `send_email` — the injectable sender, mirroring `sms.py`

**Files:**
- Create: `backend/app/email.py`
- Modify: `backend/app/settings.py` (new optional fields)
- Modify: `backend/app/main.py` (`create_app(..., email_sender=None)`, `app.state.email_sender`)
- Test: `backend/tests/test_email.py` (new)

**Interfaces:**
- Produces: `send_email(settings, to, subject, body) -> None`, raising `EmailSendError` on failure (mirrors `send_sms`/`SmsSendError` exactly). `Settings.email_provider_url/_api_key/_sender_name/_sender_address` (all optional, default `''`/`'CRM'`-style). `app.state.email_sender` (test-injectable, defaults to `send_email`). Task 3's test-send endpoint calls this exact function.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_email.py`, mirroring `backend/tests/test_sms.py`'s structure exactly (read that file first and match its fixture/assertion style precisely — do not invent a different pattern):
```python
import httpx
import pytest

from app.email import EmailSendError, send_email
from app.settings import Settings


def make_settings(**overrides):
    from helpers import make_settings as base_make_settings
    return base_make_settings('postgresql+psycopg://u:p@h:5432/db', **overrides)


def test_logs_when_no_provider_configured(caplog):
    import logging
    with caplog.at_level(logging.INFO):
        send_email(make_settings(email_provider_url=''), 'user@example.test', 'Тема', 'Текст письма')
    assert 'user@example.test' in caplog.text
    assert 'Тема' in caplog.text


def test_posts_to_provider_when_configured(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return httpx.Response(200, request=httpx.Request('POST', url))

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(
        email_provider_url='https://email.example/send', email_provider_api_key='key123',
        email_sender_address='noreply@unicrm.tech', email_sender_name='UniCRM',
    )
    send_email(settings, 'user@example.test', 'Тема', 'Текст письма')
    assert len(calls) == 1
    url, body, headers = calls[0]
    assert url == 'https://email.example/send'
    assert body['to'] == 'user@example.test'
    assert body['subject'] == 'Тема'
    assert body['text'] == 'Текст письма'
    assert body['from'] == 'noreply@unicrm.tech'
    assert headers['Authorization'] == 'Bearer key123'


def test_raises_on_provider_failure(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError('boom')

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(email_provider_url='https://email.example/send')
    with pytest.raises(EmailSendError):
        send_email(settings, 'user@example.test', 'Тема', 'Текст письма')


def test_raises_on_non_2xx_response(monkeypatch):
    def fake_post(url, json, headers, timeout):
        return httpx.Response(500, request=httpx.Request('POST', url))

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(email_provider_url='https://email.example/send')
    with pytest.raises(EmailSendError):
        send_email(settings, 'user@example.test', 'Тема', 'Текст письма')
```
Check `backend/tests/helpers.py`'s `make_settings` actually accepts arbitrary `**overrides` for fields not in its base dict (it does — `values.update(overrides)` — confirm this covers new `Settings` fields that don't have a base entry; if `Settings` is a strict dataclass this should just work since `overrides` gets passed straight to `Settings(**values)`).

- [ ] **Step 2: Run it, confirm it fails (module doesn't exist yet)**

```bash
cd backend && .venv/bin/python -m pytest tests/test_email.py -v
```

- [ ] **Step 3: Add the settings fields**

In `backend/app/settings.py`, mirror the SMS fields exactly (same style, same "optional, degrades to logging-only" comment pattern):
```python
    # Outgoing email for university correspondence (Настройки → Личный профиль). Unset in local
    # dev/CI on purpose, same as sms_provider_url: app/email.py falls back to a logging-only sender
    # so the code is visible (API container log) without any real provider account. Real credentials
    # are supplied only through deploy/local/api.env, never committed.
    email_provider_url: str = ''
    email_provider_api_key: str = ''
    email_sender_name: str = 'UniCRM'
    email_sender_address: str = ''
```
In `load_settings()`:
```python
        email_provider_url=(environ.get('EMAIL_PROVIDER_URL') or '').strip(),
        email_provider_api_key=(environ.get('EMAIL_PROVIDER_API_KEY') or '').strip(),
        email_sender_name=(environ.get('EMAIL_SENDER_NAME') or '').strip() or 'UniCRM',
        email_sender_address=(environ.get('EMAIL_SENDER_ADDRESS') or '').strip(),
```

- [ ] **Step 4: Implement `backend/app/email.py`**

Read `backend/app/sms.py` in full first and mirror its exact structure (module docstring explaining the same "no real gateway, logging-only fallback, generic invented HTTP contract with a warning for whoever wires up a real one" reasoning, adapted for email):
```python
"""Injectable email sending for outgoing university correspondence (Настройки → Личный профиль).

No real email provider is integrated in this environment (no credentials or provider API spec
were available). `send_email` picks one of two concrete implementations based on
`settings.email_provider_url`:

- Unset (the default in local dev/CI): a logging-only sender. The recipient, subject and body are
  written to the API container's log at INFO level and the call returns as if the email had been
  sent — same transparency as app/sms.py's own logging-only fallback.
- Set: a generic, best-effort HTTP POST to `email_provider_url`:
    POST {email_provider_url}
    Authorization: Bearer {email_provider_api_key}
    Content-Type: application/json
    {"to": "<address>", "from": "<email_sender_address>", "subject": "<subject>", "text": "<body>"}
  Any non-2xx response (or a network failure) raises EmailSendError so the caller fails closed.

  IMPORTANT for whoever wires up a real provider later: this request/response shape is NOT a real
  provider's documented API — it was invented as a plausible generic contract, exactly like
  app/sms.py's own disclaimer. Replace the body of `_http_sender` with a call matching the real
  provider's request fields, auth scheme, and success/error response shape before pointing
  EMAIL_PROVIDER_URL at anything real.

The `sender` parameter (defaulting to the module's own settings-based choice) is what makes this
injectable: app/main.py stores the chosen callable on app.state.email_sender (defaulting to
send_email itself), and tests substitute a fake there — same pattern as app.state.sms_sender.
"""
import logging

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0


class EmailSendError(RuntimeError):
    """Raised when an email could not be sent; the caller is expected to fail closed on this."""


def _log_sender(settings, to, subject, body):
    logger.info('Email to %s: %s\n%s', to, subject, body)


def _http_sender(settings, to, subject, body):
    try:
        response = httpx.post(
            settings.email_provider_url,
            json={'to': to, 'from': settings.email_sender_address, 'subject': subject, 'text': body},
            headers={'Authorization': f'Bearer {settings.email_provider_api_key}'},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise EmailSendError(f'Email provider request failed: {error}') from error


def send_email(settings, to, subject, body) -> None:
    """Sends an email to `to`; raises EmailSendError on failure. See module docstring for the contract."""
    sender = _http_sender if settings.email_provider_url else _log_sender
    sender(settings, to, subject, body)
```

- [ ] **Step 5: Wire it into `create_app()`**

In `backend/app/main.py`, mirror the existing `sms_sender` wiring exactly:
```python
def create_app(settings=None, *, http_client=None, sms_sender=None, email_sender=None):
    ...
    app.state.sms_sender = sms_sender or send_sms
    app.state.email_sender = email_sender or send_email
```
Import `send_email` from `.email` alongside the existing `send_sms` import.

- [ ] **Step 6: Run the tests, confirm they pass; run the full backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/test_email.py -v
cd backend && .venv/bin/python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/email.py backend/app/settings.py backend/app/main.py backend/tests/test_email.py
git commit -m "feat(email): add injectable outgoing-email sending, mirroring the SMS pattern"
```

---

### Task 2: Sender-identity catalog + `User.email_sender_identity_id`

**Files:**
- Create: `backend/migrations/versions/0015_email_sender_identities.py`
- Modify: `backend/app/models.py` (`EmailSenderIdentity`, `User.email_sender_identity_id`)
- Create: `backend/app/email_routes.py`
- Modify: `backend/app/main.py` (register the new router)
- Test: `backend/tests/test_email_senders.py` (new)

**Interfaces:**
- Produces: `GET /api/v1/email-senders` (any signed-in user — lists approved identities to choose from), `POST /api/v1/email-senders` (supervisor/admin only — creates one, always approved since only admins can create), `DELETE /api/v1/email-senders/{id}` (supervisor/admin only — deactivates, never hard-deletes if it's ever been selected by a user, matching this codebase's general soft-delete-over-hard-delete caution). A later, separate plan (Личный профиль) reads this list and lets a user set their own `email_sender_identity_id`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_email_senders.py`, following this codebase's established test style (`client`/`keycloak`/`database_url` fixtures, `login()` from `helpers.py` — check `backend/tests/test_task_api.py` or similar for the exact request/assertion idioms and match them):
```python
def test_only_supervisor_and_admin_can_create_a_sender_identity(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders', json={
        'email_address': 'info@unicrm.tech', 'display_name': 'UniCRM — общая почта',
    })
    assert response.status_code == 403


def test_supervisor_can_create_and_it_is_immediately_approved(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    response = client.post('/api/v1/email-senders', json={
        'email_address': 'info@unicrm.tech', 'display_name': 'UniCRM — общая почта',
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body['email_address'] == 'info@unicrm.tech'
    assert body['is_active'] is True


def test_rejects_an_invalid_email_address(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    response = client.post('/api/v1/email-senders', json={
        'email_address': 'not-an-email', 'display_name': 'Тест',
    })
    assert response.status_code == 422


def test_any_signed_in_user_can_list_active_senders(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    client.post('/api/v1/email-senders', json={'email_address': 'info@unicrm.tech', 'display_name': 'Общая почта'})
    login(client, keycloak, roles=('crm-user',))
    response = client.get('/api/v1/email-senders')
    assert response.status_code == 200
    assert any(s['email_address'] == 'info@unicrm.tech' for s in response.json())


def test_deactivating_removes_it_from_the_selectable_list(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    created = client.post('/api/v1/email-senders', json={'email_address': 'info@unicrm.tech', 'display_name': 'Общая почта'}).json()
    response = client.delete(f"/api/v1/email-senders/{created['id']}")
    assert response.status_code == 204
    listing = client.get('/api/v1/email-senders').json()
    assert not any(s['id'] == created['id'] for s in listing)


def test_only_supervisor_and_admin_can_deactivate(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    created = client.post('/api/v1/email-senders', json={'email_address': 'info@unicrm.tech', 'display_name': 'Общая почта'}).json()
    login(client, keycloak, roles=('crm-user',))
    response = client.delete(f"/api/v1/email-senders/{created['id']}")
    assert response.status_code == 403
```

- [ ] **Step 2: Run it, confirm it fails**

```bash
cd backend && .venv/bin/python -m pytest tests/test_email_senders.py -v
```

- [ ] **Step 3: Add the model**

In `backend/app/models.py`, add near `User` (check imports for `Boolean`/`String`/`ForeignKey`/`utcnow` already used elsewhere in this file and reuse them):
```python
class EmailSenderIdentity(Base):
    """A "from" address a user may send university correspondence as (Настройки → Личный профиль).
    Every row is inherently admin-approved: only crm-supervisor/crm-admin can create one — there is
    no self-service "verify my own mailbox" flow. Deactivated (is_active=False), never hard-deleted,
    so a user who previously selected one keeps a valid historical reference.
    """
    __tablename__ = 'email_sender_identities'
    id: Mapped[int] = mapped_column(primary_key=True)
    email_address: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(russian_text(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```
Add to `User`:
```python
    email_sender_identity_id: Mapped[int | None] = mapped_column(ForeignKey('email_sender_identities.id'))
```
(nullable — no sender selected is a normal default state).

- [ ] **Step 4: Write the migration**

`backend/migrations/versions/0015_email_sender_identities.py` — follow this repo's existing migration style (check a recent one, e.g. `0013_task_board_columns.py`, for the exact `op.create_table`/`op.f(...)` naming-convention pattern and mirror it precisely, including the `downgrade()`):
```python
"""email sender identities

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'email_sender_identities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_address', sa.String(length=254), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('email_sender_identities_pkey')),
        sa.UniqueConstraint('email_address', name=op.f('email_sender_identities_email_address_key')),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('email_sender_identities_created_by_user_id_fkey')),
    )
    op.add_column('users', sa.Column('email_sender_identity_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('users_email_sender_identity_id_fkey'), 'users', 'email_sender_identities',
        ['email_sender_identity_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint(op.f('users_email_sender_identity_id_fkey'), 'users', type_='foreignkey')
    op.drop_column('users', 'email_sender_identity_id')
    op.drop_table('email_sender_identities')
```
Check the exact `russian_text()` collation helper's column type/length conventions used for `display_name` elsewhere in `models.py` and make sure the migration's `sa.String(length=200)` matches whatever that helper actually produces (it may need the same ICU-collation `String` variant other Russian-text columns use — check e.g. how `University.name`'s migration column was defined, and mirror it exactly, not a plain `String`).

- [ ] **Step 5: Implement the endpoints**

`backend/app/email_routes.py`:
```python
"""Sender-identity catalog for outgoing university correspondence (Настройки → Личный профиль).
Every identity is admin-created and therefore inherently approved — see EmailSenderIdentity's
docstring in models.py for why there is no separate self-service verification flow.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import EmailSenderIdentity

router = APIRouter(prefix='/api/v1/email-senders', tags=['Отправители писем'])
any_role = require_roles(*ALL_ROLES)
sender_manager = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)

DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SenderIn(BaseModel):
    email_address: EmailStr
    display_name: DisplayName


class SenderOut(BaseModel):
    id: int
    email_address: str
    display_name: str
    is_active: bool


def sender_out(row):
    return SenderOut(id=row.id, email_address=row.email_address, display_name=row.display_name, is_active=row.is_active)


@router.get('', response_model=list[SenderOut], summary='Список доступных отправителей', dependencies=[Depends(any_role)])
def list_senders(db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailSenderIdentity).where(EmailSenderIdentity.is_active.is_(True)).order_by(EmailSenderIdentity.display_name)).all()
    return [sender_out(r) for r in rows]


@router.post('', response_model=SenderOut, status_code=201, summary='Добавить отправителя')
def create_sender(data: SenderIn, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    existing = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.email_address == data.email_address))
    if existing is not None:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'email_address', 'message': 'Такой адрес уже добавлен', 'type': 'value_error'}])
    row = EmailSenderIdentity(email_address=data.email_address, display_name=data.display_name, created_by_user_id=auth.user.id)
    db.add(row)
    db.flush()
    record_event(db, request, auth.user, 'email_sender.create', entity_type='email_sender_identity', entity_id=row.id,
                 summary=f'Добавлен отправитель писем «{row.display_name}» ({row.email_address})', payload={'email_address': row.email_address})
    db.commit()
    return sender_out(row)


@router.delete('/{sender_id}', status_code=204, summary='Деактивировать отправителя')
def deactivate_sender(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = db.get(EmailSenderIdentity, sender_id)
    if row is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    row.is_active = False
    record_event(db, request, auth.user, 'email_sender.deactivate', entity_type='email_sender_identity', entity_id=row.id,
                 summary=f'Деактивирован отправитель писем «{row.display_name}» ({row.email_address})', payload={})
    db.commit()
```
Check `AppError`/`ErrorCode`/`record_event`'s exact call signatures against how they're already used elsewhere (e.g. `plan_routes.py`) before finalizing — match this codebase's established error/audit patterns exactly, don't invent a slightly different shape.

- [ ] **Step 6: Register the router**

In `backend/app/main.py`, import and register `email_routes.router` the same way `profile_routes.router` already is.

- [ ] **Step 7: Run the tests, confirm they pass; run the full backend suite; check the migration**

```bash
cd backend && .venv/bin/python -m pytest tests/test_email_senders.py -v
cd backend && .venv/bin/python -m pytest -q
cd backend && alembic upgrade head && alembic check
```

- [ ] **Step 8: Commit**

```bash
git add backend/migrations/versions/0015_email_sender_identities.py backend/app/models.py backend/app/email_routes.py backend/app/main.py backend/tests/test_email_senders.py
git commit -m "feat(email): add an admin-managed sender-identity catalog"
```

---

### Task 3: Safe test-send-to-self

**Files:**
- Modify: `backend/app/email_routes.py`
- Test: `backend/tests/test_email_senders.py`

**Interfaces:**
- Produces: `POST /api/v1/email-senders/test` (any signed-in user) — sends a short test message via `app.state.email_sender`, to the caller's own Keycloak-sourced email (`auth.user.email`, never an arbitrary address the client supplies — this is a safety property, not an oversight: a test-send endpoint that could target any address would be an open mail-relay-testing primitive), using the caller's currently-selected `email_sender_identity_id` as the "from" if set, or the system default sender name/address otherwise. Response says plainly whether the email was actually sent or only logged (i.e., whether `settings.email_provider_url` is configured) — this is the one place the "never claim sending works when unconfigured" constraint becomes user-visible, not just a code comment.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_email_senders.py`:
```python
def test_test_send_reports_logged_only_when_no_provider_configured(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['delivered'] is False
    assert 'не настроен' in body['message'].lower() or 'журнал' in body['message'].lower()


def test_test_send_uses_the_callers_own_email_never_a_supplied_address(client, keycloak, app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body: sent.append((to, subject, body))
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 200
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == 'anna.demo@demo.local'  # matches this fixture's default logged-in user's email — confirm the real value against helpers.py/fake_keycloak.py rather than assuming


def test_test_send_reports_delivered_true_when_a_sender_is_injected(client, keycloak, app):
    app.state.email_sender = lambda settings, to, subject, body: None
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.json()['delivered'] is True


def test_test_send_surfaces_a_send_failure_as_a_service_error(client, keycloak, app):
    from app.email import EmailSendError

    def failing_sender(settings, to, subject, body):
        raise EmailSendError('provider down')

    app.state.email_sender = failing_sender
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 503
```
Check the `app` fixture's exact settings (`email_provider_url` — is it unset by default in `helpers.make_settings`, matching "no provider configured" for the first test? Confirm directly) and the logged-in test user's actual email value (`fake_keycloak.py`'s default `issue_code(...)` email) before finalizing these assertions — don't guess the literal string.

- [ ] **Step 2: Run it, confirm it fails**

```bash
cd backend && .venv/bin/python -m pytest tests/test_email_senders.py -k test_send -v
```

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/email_routes.py`:
```python
class TestSendOut(BaseModel):
    delivered: bool
    message: str


@router.post('/test', response_model=TestSendOut, summary='Отправить тестовое письмо на свой адрес')
def test_send(request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    sender = getattr(request.app.state, 'email_sender', None)
    configured = bool(settings.email_provider_url)
    from_identity = db.get(EmailSenderIdentity, auth.user.email_sender_identity_id) if auth.user.email_sender_identity_id else None
    from_label = from_identity.email_address if from_identity else settings.email_sender_address or settings.email_sender_name
    subject = 'Тестовое письмо UniCRM'
    body = f'Это тестовое письмо, отправленное от имени «{from_label}». Если вы получили его, отправка почты настроена верно.'
    try:
        sender(settings, auth.user.email, subject, body)
    except Exception as error:  # EmailSendError specifically, but any sender failure should fail the same way
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось отправить письмо, попробуйте ещё раз позже') from error
    if configured:
        return TestSendOut(delivered=True, message=f'Письмо отправлено на {auth.user.email}.')
    return TestSendOut(delivered=False, message='Почтовый провайдер не настроен: письмо записано только в журнал сервера, реальная отправка недоступна.')
```
Narrow the bare `except Exception` to `except EmailSendError` specifically once you've imported it — the sketch above uses the broad form only because this snippet doesn't show the import; use the narrow, correct one in the real code.

- [ ] **Step 4: Run the tests, confirm they pass; run the full backend suite**

```bash
cd backend && .venv/bin/python -m pytest tests/test_email_senders.py -v
cd backend && .venv/bin/python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/email_routes.py backend/tests/test_email_senders.py
git commit -m "feat(email): add a safe test-send-to-self endpoint"
```

## Self-Review Notes

- **Spec coverage:** injectable email sending mirroring SMS (Task 1) ✓. Sender selection limited to verified/admin-approved identities, never a raw self-entered address (Task 2 — every identity is admin-created by construction) ✓. Test email to the user's own address, never an arbitrary one (Task 3) ✓. Never expose credentials in the browser (nothing in any task returns `email_provider_api_key`/`email_provider_url` to the client — `SenderOut`/`TestSendOut` schemas contain no credential fields) ✓. Never claim sending works when unconfigured (Task 3's `delivered`/`message` fields make this explicit and user-visible, not just a server log line) ✓.
- **Placeholder scan:** no TBD/"add later" left unfollowed; every code block is complete and runnable.
- **Type/name consistency:** `send_email(settings, to, subject, body)` signature identical across Task 1's definition, Task 3's usage, and both tasks' tests. `EmailSenderIdentity`/`SenderOut`/`TestSendOut` field names consistent between Task 2's model/schema and Task 3's usage of `auth.user.email_sender_identity_id`.
