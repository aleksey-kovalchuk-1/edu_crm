# Личный профиль и адреса отправителей — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Редактируемый профиль (имя/фамилия в Keycloak, телефон без подтверждения, часовой пояс, мессенджеры), устойчивая к переименованию связь ответственного по взаимодействию и адреса отправителей с одобрением руководителя и подтверждением по email.

**Architecture:** Одна миграция `0025` поверх `0024` ветки GPT. Бэкенд: новые модули `app/owner_links.py` (сопоставление ответственного и каскад переименования), `app/sender_addresses.py` (проверка адреса перед отправкой и токены подтверждения); `profile_routes.py` переписывается под `GET/PATCH /profile`; `email_routes.py` получает заявки, одобрение и подтверждение. Фронтенд: переписанная страница профиля, панель очереди в «Организации», публичная страница `/confirm-sender`.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16, httpx (Keycloak Admin API), pytest с `FakeKeycloak`; React 19 + TypeScript + TanStack Query + React Router 7, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-27-profile-and-sender-addresses-design.md`

## Global Constraints

- Ветка реализации создаётся от коммита GPT `326ac7f` (ветка `codex/customer-data`), не от `ai/design-tokens`. Незакоммиченное изменение GPT в `backend/tests/fake_keycloak.py` в его рабочей копии не трогать и не переносить.
- Миграция: `revision = '0025'`, `down_revision = '0024'`.
- Имя: 1–100 символов каждое после обрезки; `full_name = f'{first_name} {last_name}'`, ≤ 200.
- Часовой пояс по умолчанию `Europe/Moscow`, проверка `zoneinfo.ZoneInfo`.
- Отчество: до 100 символов, необязательное; Keycloak `attributes.middleName`; в `full_name` не входит.
- Telegram: `^[A-Za-z0-9_]{5,32}$` после обрезки `@`; WhatsApp: `+7XXXXXXXXXX` через `normalize_phone`; пустая строка очищает; статус «Не указан» / «Сохранён · не подключён».
- Телефон профиля: только через SMS-подтверждение; номер должен начинаться с `+79`: «Укажите мобильный номер в формате +7 9XX XXX-XX-XX».
- Токен подтверждения: действует 48 часов, одноразовый, хранится только `security.token_hash`; повторная отправка не чаще раза в 60 секунд.
- Сообщение отказа адреса: `'Выбранный адрес отправителя недоступен — выберите другой в профиле'`.
- Сообщение неверного токена: `'Ссылка недействительна или устарела'`.
- Не изменять: `app/phone.py`, `app/sms.py`, `catalog_routes.py`, `customer_imports.py`, `learner_routes.py`, `vendor_routes.py`, телефонные столбцы контактов, вендоров и слушателей.
- SMS-подтверждение телефона (`/profile/phone`, `/profile/phone/verify`) сохраняется со всей его логикой.
- Существующие строки `email_sender_identities` и значения `users.email_sender_identity_id` сохраняются без изменений.
- Не пушить и не сливать; только локальные коммиты. Не трогать рабочую систему (`compose.public.yaml`, `unicrm.tech`) — выпуск отдельным решением владельца.
- Сообщения коммитов заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Ревизия 27.09.2026 (заменяет соответствующие места задач ниже)

Владелец изменил срез 1 (см. раздел «Ревизия» спецификации). Там, где текст задачи ниже расходится с этим блоком, действует этот блок.

- **Task 1.** В `users` вместо `messengers` добавить `middle_name varchar(100) default ''`, `telegram varchar(32) default ''`, `whatsapp varchar(16) default ''` (миграция, `downgrade` и модель `User`). В тесте миграции `user_row` выбирает `first_name, middle_name, last_name, timezone, telegram, whatsapp` и ожидает `('', '', '', 'Europe/Moscow', '', '')`.
- **Task 3.** Метод называется `update_user_names(user_id, *, first_name, last_name, middle_name)`: кроме `firstName`/`lastName` пишет `representation.setdefault('attributes', {})['middleName'] = [middle_name] if middle_name else []`. Тест проверяет, что `attributes` сохраняет прочие ключи и получает `middleName`. Добавить в этот же таск: `scripts/keycloak-add-middle-name.sh` (вход `kcadm` как в `scripts/keycloak-add-public-origin.sh`; `kcadm.sh get users/profile -r edu-crm` → если атрибута `middleName` нет, добавить `{"name":"middleName","displayName":"Отчество","validations":{"length":{"max":100}},"permissions":{"view":["admin","user"],"edit":["admin"]},"multivalued":false}` и `kcadm.sh update users/profile -r edu-crm -f -`; повторный запуск ничего не меняет) и то же объявление атрибута в `deploy/keycloak/realm-edu-crm.json` (компонент `org.keycloak.userprofile.UserProfileProvider` / `kc.user.profile.config`; если в JSON его нет — добавить конфигурацию профиля по умолчанию Keycloak 26 плюс `middleName`). Запускать скрипт против живого realm — только с разрешения владельца, в Task 12.
- **Task 5.** `profile_routes.py` **не переписывается целиком**: существующие `request_phone_code`/`verify_phone_code` и их помощники остаются; в `request_phone_code` после `normalize_phone` добавить `if not phone.startswith('+79'): raise AppError(VALIDATION_ERROR, details=[{'field': 'phone', 'message': 'Укажите мобильный номер в формате +7 9XX XXX-XX-XX', 'type': 'value_error'}])`. `test_phone_verification.py` не удаляется; добавить в него тест, что `+74951234567` отклоняется `422` и SMS не отправляется. `GET/PATCH /profile` добавляются в тот же файл; `ProfilePatch` = `first_name`, `middle_name` (0–100, `None` — не менять), `last_name`, `timezone`, `telegram`, `whatsapp`, `email_sender_identity_id` — **без** `phone` и `messengers`. `ProfileOut` = `id, email, first_name, middle_name, last_name, full_name, phone, phone_verified_at, timezone, telegram, whatsapp, email_sender_identity_id`. Изменение отчества тоже вызывает Keycloak (`update_user_names`), но не каскад (`full_name` не меняется). Тесты Task 5: заменить `messengers`-тесты на Telegram/WhatsApp (валидный `@anna_demo` → `anna_demo`; `ab` → 422 по `telegram`; `+7 999 123-45-67` → `+79991234567`; `12` → 422 по `whatsapp`), убрать тест «phone endpoints are gone» и ожидание `phone` в `PATCH`; добавить: `PATCH {'phone': ...}` не меняет телефон (поле игнорируется — в `ProfilePatch` задать `model_config = ConfigDict(extra='forbid')`, тогда 422); отчество пишется в Keycloak `attributes.middleName`. `/auth/me`: добавить `first_name, middle_name, last_name, timezone, telegram, whatsapp`; `phone_verified_at` **оставить**.
- **Task 8.** `profile.ts`: оставить `isPlausiblePhone`, `useRequestPhoneCode`, `useVerifyPhoneCode`; `isPlausiblePhone` проверяет `+79`/`89`/`79` + 9 цифр (11 цифр, вторая `9`). Типы `Profile`/`ProfilePatch` — по полям Task 5; вместо `MESSENGER_*` экспортировать `contactStatus(value: string): "Не указан" | "Сохранён · не подключён"`; тест `profile.test.ts` проверяет `contactStatus` и `isPlausiblePhone("+74951234567") === false`. `CurrentUser` и `sessionFixture` сохраняют `phone_verified_at` и получают новые поля.
- **Task 9.** Страница: панель «Личные данные» (Имя, Отчество, Фамилия, Email только чтение, Часовой пояс, Telegram, WhatsApp — у каждого контакта подпись статуса из `contactStatus`), кнопка «Сохранить»; ниже — панель «Мобильный телефон» с существующим SMS-процессом (перенести разметку шагов `view/phone/code` из текущей страницы, поменять подпись на «Мобильный телефон», подсказку на «Формат: +7 9XX XXX-XX-XX», баннер — на строку «Номер не подтверждён»; пока код не подтверждён, введённый номер показывается только с пометкой «Ожидает подтверждения»); затем `SenderAddressPanel`. Тесты: сохранение имени/отчества/Telegram/WhatsApp одним `PATCH` (тело без `phone`); ошибка Keycloak оставляет форму заполненной; `+7 495…` отклоняется локально без запроса; после запроса кода, до подтверждения, нет текста «Подтверждён»; статус «Сохранён · не подключён» у заполненного Telegram; прежние тесты подтверждения телефона сохраняются с обновлёнными подписями.
- **Task 12.** В `docs/decisions.md` вместо «отмена SMS-подтверждения» записать: мобильный `+79…` для SMS-подтверждения; отчество в Keycloak; Telegram/WhatsApp — только сохранённые контакты без интеграции. С разрешения владельца запустить `scripts/keycloak-add-middle-name.sh` против живого realm и проверить `kcadm.sh get users/profile`.

## Review Focus

- Пользователь сохраняет своё же имя в другом регистре или с пробелами («анна петрова» вместо «Анна Петрова») — это не конфликт с самим собой; ожидается успешное сохранение. Тест в Task 5.
- Keycloak Admin не настроен, а пользователь меняет только телефон или часовой пояс — ожидается успешное сохранение без обращения к Keycloak. Тест в Task 5.
- Ссылка подтверждения открыта после того, как адрес деактивировали или заявку отозвали — ожидается «Ссылка недействительна или устарела», адрес не становится активным. Тест в Task 7.
- Двойное нажатие «Подтвердить» — первое подтверждает, второе получает «недействительна», адрес остаётся активным. Тест в Task 7.
- Ответственный набран с лишними пробелами или в другом регистре — взаимодействие всё равно связывается; деактивированный однофамилец не мешает сопоставлению. Тест в Task 2.

---

### Task 0: Рабочая копия от ветки GPT

**Files:** нет изменений кода.

- [ ] **Step 1: Создать рабочую копию**

```bash
cd /Users/alex/dev/edu-crm
git worktree add .worktrees/profile-senders -b ai/profile-senders 326ac7f
cd .worktrees/profile-senders
```

- [ ] **Step 2: Перенести спецификацию и план в ветку**

```bash
git checkout ai/design-tokens -- docs/superpowers/specs/2026-09-27-profile-and-sender-addresses-design.md
cp /Users/alex/dev/edu-crm/docs/superpowers/plans/2026-09-27-profile-and-sender-addresses.md docs/superpowers/plans/
git add docs/superpowers/specs/2026-09-27-profile-and-sender-addresses-design.md docs/superpowers/plans/2026-09-27-profile-and-sender-addresses.md
git commit -m "docs: add profile and sender address spec and plan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Убедиться, что база тестов зелёная**

Run: `docker compose up -d db && cd backend && uv run pytest -q` (в каталоге рабочей копии)
Expected: все тесты проходят (у GPT было 474). Во фронтенде: `cd ../frontend && npm ci && npx vitest run` — все проходят. Если что-то красное до начала работы — остановиться и сообщить.

---

### Task 1: Миграция 0025 и модели

**Files:**
- Create: `backend/migrations/versions/0025_profile_and_sender_addresses.py`
- Modify: `backend/app/models.py` (`Launch` ~стр. 53, `EmailSenderIdentity` ~стр. 360, `User` ~стр. 375)
- Test: `backend/tests/test_profile_sender_migration.py`

**Interfaces:**
- Produces: `User.first_name: str`, `User.last_name: str`, `User.timezone: str`, `User.messengers: list[dict]`; `Launch.owner_user_id: int | None`, `Launch.owner` длиной 200; `EmailSenderIdentity.owner_user_id`, `.status`, `.requested_by_user_id`, `.requested_at`, `.approved_by_user_id`, `.approved_at`, `.rejection_reason`, `.confirmation_token_hash`, `.confirmation_expires_at`, `.confirmation_sent_at`, `.confirmed_at`; константа `SENDER_STATUSES = ('pending_approval', 'awaiting_confirmation', 'active', 'rejected')` в `models.py`.

- [ ] **Step 1: Написать падающий тест миграции**

`backend/tests/test_profile_sender_migration.py`:

```python
from alembic import command
from sqlalchemy import create_engine, text

from app.db_migrate import alembic_config


def _seed_0024(connection):
    university_id = connection.execute(text(
        "insert into universities (name, city, contact) values ('Вуз', 'Москва', '') returning id"
    )).scalar_one()
    template_id, status_id = connection.execute(text(
        "select template_id, id from workflow_statuses where position = 0 "
        "and template_id = (select id from workflow_templates where is_default)"
    )).one()

    def user(sub, name, active=True):
        return connection.execute(text(
            "insert into users (keycloak_sub, email, full_name, roles, is_active, created_at) "
            "values (:sub, :sub || '@x.test', :name, '{crm-user}', :active, now()) returning id"
        ), {'sub': sub, 'name': name, 'active': active}).scalar_one()

    def launch(owner):
        return connection.execute(text(
            "insert into launches (university_id, program, product, owner, students, stage, deadline, "
            "workflow_template_id, status_id) values (:u, 'Python', 'Среда', :owner, 1, 0, '2026-10-01', :t, :s) "
            "returning id"
        ), {'u': university_id, 'owner': owner, 't': template_id, 's': status_id}).scalar_one()

    anna = user('kc-anna', 'Анна Петрова')
    user('kc-ivan-1', 'Иван Иванов')
    user('kc-ivan-2', 'иван иванов')
    user('kc-old', 'Анна Петрова', active=False)
    sender_id = connection.execute(text(
        "insert into email_sender_identities (email_address, display_name, is_active, created_at) "
        "values ('office@uni.test', 'Офис', true, now()) returning id"
    )).scalar_one()
    inactive_sender = connection.execute(text(
        "insert into email_sender_identities (email_address, display_name, is_active, created_at) "
        "values ('old@uni.test', 'Старый', false, now()) returning id"
    )).scalar_one()
    connection.execute(text("update users set email_sender_identity_id = :s where id = :u"), {'s': sender_id, 'u': anna})
    return {
        'anna': anna, 'sender': sender_id, 'inactive_sender': inactive_sender,
        'linked': launch('  анна петрова '), 'ambiguous': launch('Иван Иванов'), 'unmatched': launch('Уволившийся'),
    }


def test_0025_links_unique_owners_and_preserves_senders(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0024')
    engine = create_engine(empty_database_url)
    try:
        with engine.begin() as connection:
            ids = _seed_0024(connection)
        command.upgrade(config, '0025')
        with engine.connect() as connection:
            owners = dict(connection.execute(text('select id, owner_user_id from launches')).all())
            texts = dict(connection.execute(text('select id, owner from launches')).all())
            senders = {row.id: row for row in connection.execute(text(
                'select id, owner_user_id, status, is_active from email_sender_identities'))}
            selected = connection.execute(text('select email_sender_identity_id from users where id = :u'),
                                          {'u': ids['anna']}).scalar_one()
            user_row = connection.execute(text('select first_name, last_name, timezone, messengers from users where id = :u'),
                                          {'u': ids['anna']}).one()
            owner_length = connection.execute(text(
                "select character_maximum_length from information_schema.columns "
                "where table_name = 'launches' and column_name = 'owner'")).scalar_one()
    finally:
        engine.dispose()

    assert owners[ids['linked']] == ids['anna']  # the only ACTIVE match; the deactivated namesake is ignored
    assert owners[ids['ambiguous']] is None
    assert owners[ids['unmatched']] is None
    assert texts[ids['linked']] == '  анна петрова '  # backfill never rewrites text
    assert senders[ids['sender']].owner_user_id is None and senders[ids['sender']].status == 'active'
    assert senders[ids['sender']].is_active is True
    assert senders[ids['inactive_sender']].status == 'active' and senders[ids['inactive_sender']].is_active is False
    assert selected == ids['sender']
    assert tuple(user_row) == ('', '', 'Europe/Moscow', [])
    assert owner_length == 200


def test_0025_downgrade_round_trip(empty_database_url):
    config = alembic_config(empty_database_url)
    command.upgrade(config, '0025')
    command.downgrade(config, '0024')
    command.upgrade(config, '0025')
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `cd backend && uv run pytest tests/test_profile_sender_migration.py -v`
Expected: FAIL — `Can't locate revision identified by '0025'`.

- [ ] **Step 3: Написать миграцию**

`backend/migrations/versions/0025_profile_and_sender_addresses.py`:

```python
"""Editable profile fields, rename-safe interaction owners, and approved sender addresses.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None

RU = 'ru-RU-x-icu'


def upgrade() -> None:
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=False, server_default=''))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=False, server_default=''))
    op.add_column('users', sa.Column('timezone', sa.String(64), nullable=False, server_default='Europe/Moscow'))
    op.add_column('users', sa.Column('messengers', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))

    op.alter_column('launches', 'owner', type_=sa.String(200, collation=RU), existing_type=sa.String(100, collation=RU))
    op.add_column('launches', sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_launches_owner_user_id', 'launches', ['owner_user_id'])
    # Link only when exactly one ACTIVE user has the same normalized name; never rewrite the text.
    op.execute("""
        UPDATE launches l SET owner_user_id = m.user_id
        FROM (
            SELECT l2.id AS launch_id, min(u.id) AS user_id
            FROM launches l2 JOIN users u
              ON u.is_active AND lower(btrim(u.full_name)) = lower(btrim(l2.owner))
            GROUP BY l2.id HAVING count(*) = 1
        ) m
        WHERE l.id = m.launch_id
    """)

    op.add_column('email_sender_identities', sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('email_sender_identities', sa.Column('status', sa.String(32), nullable=False, server_default='active'))
    op.create_check_constraint(
        'ck_email_sender_identities_status', 'email_sender_identities',
        "status in ('pending_approval', 'awaiting_confirmation', 'active', 'rejected')",
    )
    for name, column in (
        ('requested_by_user_id', sa.Integer()), ('approved_by_user_id', sa.Integer()),
    ):
        op.add_column('email_sender_identities', sa.Column(name, column, sa.ForeignKey('users.id'), nullable=True))
    for name in ('requested_at', 'approved_at', 'confirmation_expires_at', 'confirmation_sent_at', 'confirmed_at'):
        op.add_column('email_sender_identities', sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column('email_sender_identities', sa.Column('rejection_reason', sa.String(500), nullable=False, server_default=''))
    op.add_column('email_sender_identities', sa.Column('confirmation_token_hash', sa.String(64), nullable=True))
    op.create_index('ix_email_sender_identities_owner_user_id', 'email_sender_identities', ['owner_user_id'])
    op.create_index('ix_email_sender_identities_token', 'email_sender_identities', ['confirmation_token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_email_sender_identities_token', 'email_sender_identities')
    op.drop_index('ix_email_sender_identities_owner_user_id', 'email_sender_identities')
    for name in ('confirmation_token_hash', 'rejection_reason', 'confirmed_at', 'confirmation_sent_at',
                 'confirmation_expires_at', 'approved_at', 'requested_at', 'approved_by_user_id',
                 'requested_by_user_id'):
        op.drop_column('email_sender_identities', name)
    op.drop_constraint('ck_email_sender_identities_status', 'email_sender_identities')
    op.drop_column('email_sender_identities', 'status')
    op.drop_column('email_sender_identities', 'owner_user_id')
    op.drop_index('ix_launches_owner_user_id', 'launches')
    op.drop_column('launches', 'owner_user_id')
    op.execute('UPDATE launches SET owner = left(owner, 100)')
    op.alter_column('launches', 'owner', type_=sa.String(100, collation=RU), existing_type=sa.String(200, collation=RU))
    for name in ('messengers', 'timezone', 'last_name', 'first_name'):
        op.drop_column('users', name)
```

- [ ] **Step 4: Обновить модели**

В `backend/app/models.py`:

`Launch` — заменить строку `owner` и добавить связь сразу после неё:

```python
    owner: Mapped[str] = mapped_column(russian_text(200))
    # Set when the typed owner matches exactly one active user (app/owner_links.py); a rename then
    # rewrites `owner` for these rows so assignment and report filters keep one name per person.
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
```

Перед `class EmailSenderIdentity` добавить константу, а в сам класс — поля (docstring заменить):

```python
SENDER_STATUSES = ('pending_approval', 'awaiting_confirmation', 'active', 'rejected')


class EmailSenderIdentity(Base):
    """A "from" address for university correspondence. Shared rows (owner_user_id NULL) are added by a
    supervisor/admin; personal rows are requested by their owner and approved by a supervisor/admin.
    Either kind becomes usable only after the mailbox confirms a one-time link (status 'active').
    Deactivated (is_active=False), never hard-deleted, so a stored selection stays a valid reference.
    """
    __tablename__ = 'email_sender_identities'
    __table_args__ = (
        CheckConstraint(f"status in ({', '.join(repr(s) for s in SENDER_STATUSES)})", name='status'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    email_address: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(russian_text(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    status: Mapped[str] = mapped_column(String(32), default='active', server_default='active')
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str] = mapped_column(String(500), default='', server_default='')
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    confirmation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Проверить, какое имя ограничения получает `CheckConstraint(name='status')` через `MetaData(naming_convention=...)` в `models.py` (соседние модели используют короткие имена вроде `name='valid_period'`). Если соглашение даёт `ck_email_sender_identities_status` — оставить как есть; если иное — привести имя в миграции к тому, что даёт соглашение, чтобы `alembic check` не видел расхождений.

`User` — после `full_name` добавить:

```python
    # Mirrors Keycloak firstName/lastName; the profile writes Keycloak first (app/profile_routes.py).
    first_name: Mapped[str] = mapped_column(String(100), default='', server_default='')
    last_name: Mapped[str] = mapped_column(String(100), default='', server_default='')
    timezone: Mapped[str] = mapped_column(String(64), default='Europe/Moscow', server_default='Europe/Moscow')
    # [{"service": "telegram", "handle": "anna"}]; free-text handles, no integrations.
    messengers: Mapped[list[dict]] = mapped_column(JSONB, default=list, server_default='[]')
```

- [ ] **Step 5: Запустить тест миграции и весь набор**

Run: `uv run pytest tests/test_profile_sender_migration.py -v && uv run pytest -q`
Expected: PASS; весь набор зелёный. Если есть тест сравнения моделей и миграций (`tests/test_migrations.py`) — он тоже должен пройти.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/0025_profile_and_sender_addresses.py backend/app/models.py backend/tests/test_profile_sender_migration.py
git commit -m "feat: add profile fields, interaction owner links, and sender address states

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Связь ответственного при создании взаимодействия и автоназначение

**Files:**
- Create: `backend/app/owner_links.py`
- Modify: `backend/app/schemas.py:11` (длина `owner`), `backend/app/main.py` (`add_launch`, ~стр. 169–186), `backend/app/plan_routes.py:258-266` (`resolve_assignee`)
- Test: `backend/tests/test_owner_links.py`

**Interfaces:**
- Produces: `normalize_name(value: str) -> str`; `match_owner_user(db, owner_text: str) -> int | None`; `rename_user(db, request, user, *, first_name: str, last_name: str, full_name: str) -> int` (возвращает число обновлённых взаимодействий; реализуется в Task 4, в этом таске только первые две функции).

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_owner_links.py`:

```python
from sqlalchemy import select

from app.models import Launch, User
from app.owner_links import match_owner_user
from app.plan_routes import resolve_assignee
from helpers import database, login
from test_reports import create_launch, create_university


def _user(db, sub, name, active=True):
    user = User(keycloak_sub=sub, email=f'{sub}@x.test', full_name=name, roles=['crm-user'], is_active=active)
    db.add(user)
    db.flush()
    return user


def test_match_owner_ignores_case_spaces_and_inactive_namesakes(database_url):
    with database(database_url) as db:
        anna = _user(db, 'kc-a', 'Анна Петрова')
        _user(db, 'kc-old', 'Анна Петрова', active=False)
        _user(db, 'kc-i1', 'Иван Иванов')
        _user(db, 'kc-i2', 'иван иванов')
        assert match_owner_user(db, '  анна   петрова ') == anna.id
        assert match_owner_user(db, 'Иван Иванов') is None
        assert match_owner_user(db, 'Никто') is None
        assert match_owner_user(db, '') is None


def test_created_launch_is_linked_to_the_matching_user(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-admin',), name='Ирина Петрова')
    university = create_university(client, 'Вуз связи')
    launch = create_launch(client, university['id'], owner=' ирина петрова ')
    assert launch['owner_user_id'] == me['user']['id']
    other = create_launch(client, university['id'], owner='Посторонний человек')
    assert other['owner_user_id'] is None


def test_interaction_owner_step_uses_the_link_before_text(client, keycloak, database_url):
    me = login(client, keycloak, roles=('crm-admin',), name='Ирина Петрова')
    university = create_university(client, 'Вуз назначения')
    launch_id = create_launch(client, university['id'], owner='Ирина Петрова')['id']
    with database(database_url) as db:
        launch = db.get(Launch, launch_id)
        launch.owner = 'Текст разошёлся с именем'  # simulate drift: only the link can resolve it now
        db.flush()
        step = {'assignee_rule': 'interaction_owner'}
        assert resolve_assignee(db, step, university['id'], launch, None) == (me['user']['id'], None)
        launch.owner_user_id = None
        user_id, issue = resolve_assignee(db, step, university['id'], launch, None)
        assert user_id is None and 'однозначно' in issue
```

Нормализация «несколько пробелов внутри» (`'  анна   петрова '`) требует схлопывания пробелов — `normalize_name` делает `' '.join(value.split()).casefold()`, а SQL-сторона сравнивает с `lower(regexp_replace(btrim(full_name), '\s+', ' ', 'g'))`.

- [ ] **Step 2: Запустить — должен упасть**

Run: `uv run pytest tests/test_owner_links.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.owner_links'`.

- [ ] **Step 3: Реализовать `owner_links.py`**

`backend/app/owner_links.py`:

```python
"""Interaction owner ↔ CRM user links (spec 2026-09-27, section 1.2).

`Launch.owner` stays free text typed by people; `Launch.owner_user_id` is set only when that text
matches exactly one ACTIVE user by normalized name. Plan assignment prefers the link, and a rename
rewrites `owner` on linked rows so report filters keep one value per person.
"""
from sqlalchemy import func, select

from .models import User


def normalize_name(value: str) -> str:
    return ' '.join((value or '').split()).casefold()


def _normalized_column(column):
    return func.lower(func.regexp_replace(func.btrim(column), r'\s+', ' ', 'g'))


def match_owner_user(db, owner_text: str) -> int | None:
    wanted = normalize_name(owner_text)
    if not wanted:
        return None
    ids = db.scalars(
        select(User.id).where(User.is_active.is_(True), _normalized_column(User.full_name) == wanted).limit(2)
    ).all()
    return ids[0] if len(ids) == 1 else None
```

`casefold()` в Python и `lower()` в PostgreSQL совпадают для кириллицы и латиницы; для «ß»-подобных случаев расхождение допустимо — такие имена не встречаются в данных.

- [ ] **Step 4: Подключить к созданию взаимодействия и к автоназначению**

`backend/app/schemas.py` — в `LaunchInput`:

```python
    owner: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
```

`backend/app/main.py` — импорт `from .owner_links import match_owner_user`; в `add_launch` сразу после создания `record = Launch(...)`:

```python
        record.owner_user_id = match_owner_user(db, data.owner)
```

`backend/app/plan_routes.py` — ветку `interaction_owner` заменить:

```python
    if step['assignee_rule'] == 'interaction_owner':
        if launch is None:
            return None, 'Не выбрано взаимодействие, по которому определяется ответственный'
        if launch.owner_user_id is not None:
            linked = db.get(User, launch.owner_user_id)
            if linked is not None and linked.is_active:
                return linked.id, None
        matched = match_owner_user(db, launch.owner)
        if matched is not None:
            return matched, None
        return None, 'Не удалось однозначно сопоставить ответственного по взаимодействию с пользователем CRM'
```

и импорт `from .owner_links import match_owner_user`. Если `func` в `plan_routes.py` больше нигде не используется — убрать его из импорта.

- [ ] **Step 5: Запустить тесты**

Run: `uv run pytest tests/test_owner_links.py tests/test_plan_templates.py tests/test_reports.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/owner_links.py backend/app/schemas.py backend/app/main.py backend/app/plan_routes.py backend/tests/test_owner_links.py
git commit -m "feat: link interaction owners to CRM users and prefer the link for assignment

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Обновление имени в Keycloak

**Files:**
- Modify: `backend/app/keycloak_admin.py` (метод рядом с `set_user_enabled`)
- Modify: `backend/tests/fake_keycloak.py` (`GET users/{id}` в `_admin_handler`)
- Test: `backend/tests/test_keycloak_admin.py`

**Interfaces:**
- Produces: `KeycloakAdminClient.update_user_names(user_id: str, *, first_name: str, last_name: str) -> None` — читает полное представление и отправляет его обратно с новыми `firstName`/`lastName`; ошибки — `KeycloakAdminError`/`KeycloakAdminUnavailable`. Task 5 вызывает его.

- [ ] **Step 1: Написать падающий тест**

В конец `backend/tests/test_keycloak_admin.py` (использовать фикстуру клиента, которой уже пользуются соседние тесты этого файла — посмотреть её имя в начале файла, например `admin_client`):

```python
def test_update_user_names_keeps_other_attributes(admin_client, keycloak):
    keycloak.add_admin_user(id='kc-9', email='anna@x.test', username='anna', roles=['crm-user'],
                            first_name='Анна', last_name='Петрова')
    keycloak.admin_users['kc-9']['attributes'] = {'department': ['sales']}
    admin_client.update_user_names('kc-9', first_name='Анна', last_name='Смирнова')
    stored = keycloak.admin_users['kc-9']
    assert (stored['firstName'], stored['lastName']) == ('Анна', 'Смирнова')
    assert stored['username'] == 'anna' and stored['email'] == 'anna@x.test'
    assert stored['attributes'] == {'department': ['sales']}


def test_update_user_names_for_missing_user_raises(admin_client, keycloak):
    with pytest.raises(KeycloakAdminError):
        admin_client.update_user_names('kc-missing', first_name='А', last_name='Б')
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `uv run pytest tests/test_keycloak_admin.py -k update_user_names -v`
Expected: FAIL — `AttributeError: ... has no attribute 'update_user_names'`.

- [ ] **Step 3: Добавить `GET users/{id}` в фейк**

В `FakeKeycloak._admin_handler` перед веткой `PUT/DELETE users/{id}`:

```python
        if suffix.startswith('users/') and request.method == 'GET' and '/' not in suffix[len('users/'):]:
            user = self.admin_users.get(suffix[len('users/'):])
            if user is None:
                return httpx.Response(404)
            return httpx.Response(200, json={k: v for k, v in user.items() if k not in ('roles', 'temporary_password')})
```

Там же, в ветке `PUT users/{id}`, после `self.admin_users[user_id].update(...)` синхронизировать выданные токены, как это делает настоящий Keycloak при следующем обновлении токена:

```python
                body = json.loads(request.content)
                if 'firstName' in body or 'lastName' in body:
                    stored = self.admin_users[user_id]
                    for claims in self.refresh_tokens.values():
                        if claims['sub'] == user_id:
                            claims.update(given_name=stored.get('firstName', ''), family_name=stored.get('lastName', ''),
                                          name=f"{stored.get('firstName', '')} {stored.get('lastName', '')}".strip())
```

(`json.loads(request.content)` уже вызывается выше в этой ветке — переиспользовать результат, а не парсить дважды.) Без этого проверка сессии в тестах после переименования вернула бы старое имя из токена.

- [ ] **Step 4: Реализовать метод клиента**

В `KeycloakAdminClient` после `set_user_enabled`:

```python
    def update_user_names(self, user_id, *, first_name, last_name):
        """Read-modify-write: Keycloak's declarative user profile can drop attributes a partial PUT
        omits, so the full representation goes back with only the two names changed."""
        representation = self._json(self._request('GET', f'/users/{user_id}'))
        if not isinstance(representation, dict):
            raise KeycloakAdminError('unexpected user representation shape')
        representation.update(firstName=first_name, lastName=last_name)
        self._request('PUT', f'/users/{user_id}', json=representation)
```

- [ ] **Step 5: Запустить тесты**

Run: `uv run pytest tests/test_keycloak_admin.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/keycloak_admin.py backend/tests/fake_keycloak.py backend/tests/test_keycloak_admin.py
git commit -m "feat: update Keycloak first and last name without dropping other attributes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Каскад переименования и синхронизация при входе

**Files:**
- Modify: `backend/app/owner_links.py` (функция `rename_user`)
- Modify: `backend/app/oidc.py` (`Identity`, ~стр. 40 и ~стр. 130)
- Modify: `backend/app/auth.py` (callback upsert ~стр. 155–170; `_revalidate` ~стр. 262–264)
- Modify: `backend/tests/fake_keycloak.py` (`issue_code` принимает `given_name`, `family_name`)
- Test: `backend/tests/test_rename_cascade.py`

**Interfaces:**
- Consumes: `match_owner_user` (Task 2).
- Produces: `rename_user(db, request, user, *, first_name, last_name, full_name) -> int` — записывает три поля пользователя; если `full_name` изменился — `UPDATE launches SET owner = :full_name WHERE owner_user_id = :id` и событие `user.renamed` с `payload={'from', 'to', 'launches'}`; возвращает число обновлённых строк (0, если имя не менялось). Не коммитит. `Identity.given_name: str`, `Identity.family_name: str`.

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_rename_cascade.py`:

```python
from sqlalchemy import select

from app.models import AuditEvent, Launch
from helpers import database, login, make_sessions_stale
from test_reports import create_launch, create_university


def _rename_in_keycloak(keycloak, subject, name):
    for claims in keycloak.refresh_tokens.values():
        if claims['sub'] == subject:
            claims['name'] = name


def test_login_sync_rename_rewrites_linked_launches_only(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    university = create_university(client, 'Вуз каскада')
    linked = create_launch(client, university['id'], owner='Ирина Петрова')['id']
    unlinked = create_launch(client, university['id'], owner='Сторонний Менеджер')['id']

    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Смирнова')

    with database(database_url) as db:
        assert db.get(Launch, linked).owner == 'Ирина Смирнова'
        assert db.get(Launch, unlinked).owner == 'Сторонний Менеджер'
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == 'user.renamed'))
        assert event.payload == {'from': 'Ирина Петрова', 'to': 'Ирина Смирнова', 'launches': 1}


def test_session_revalidation_rename_runs_the_same_cascade(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    university = create_university(client, 'Вуз проверки сессии')
    linked = create_launch(client, university['id'], owner='Ирина Петрова')['id']
    _rename_in_keycloak(keycloak, 'kc-irina', 'Ирина Смирнова')
    make_sessions_stale(database_url)
    assert client.get('/api/v1/auth/me').json()['user']['full_name'] == 'Ирина Смирнова'
    with database(database_url) as db:
        assert db.get(Launch, linked).owner == 'Ирина Смирнова'


def test_unchanged_name_writes_no_rename_event(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова')
    with database(database_url) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'user.renamed')) is None


def test_login_fills_first_and_last_name_from_token(client, keycloak, database_url):
    from helpers import finish_login, start_login
    response = finish_login(client, keycloak, start_login(client), roles=('crm-user',), subject='kc-n',
                            name='Олег Сидоров', email='oleg@x.test', given_name='Олег', family_name='Сидоров')
    assert response.status_code == 302
    with database(database_url) as db:
        from app.models import User
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-n'))
        assert (user.first_name, user.last_name) == ('Олег', 'Сидоров')
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `uv run pytest tests/test_rename_cascade.py -v`
Expected: FAIL — владелец остаётся «Ирина Петрова»; `issue_code()` не принимает `given_name`.

- [ ] **Step 3: Фейк и `Identity`**

`fake_keycloak.py` — сигнатура и claims в `issue_code`:

```python
    def issue_code(self, *, nonce, code_challenge, subject='kc-user-1', email='anna.demo@demo.local', name='Анна Демо',
                   roles=('crm-user',), given_name=None, family_name=None):
        code = secrets.token_urlsafe(16)
        claims = {'sub': subject, 'email': email, 'name': name, 'roles': list(roles)}
        if given_name is not None:
            claims['given_name'] = given_name
        if family_name is not None:
            claims['family_name'] = family_name
        self.codes[code] = {'claims': claims, 'nonce': nonce, 'code_challenge': code_challenge}
        return code
```

`oidc.py` — в `Identity` добавить поля со значениями по умолчанию (в конце, чтобы не ломать позиционные вызовы):

```python
    given_name: str = ''
    family_name: str = ''
```

и в `return Identity(...)` добавить `given_name=claims.get('given_name') or '', family_name=claims.get('family_name') or ''`.

- [ ] **Step 4: `rename_user`**

Добавить в `backend/app/owner_links.py`:

```python
from sqlalchemy import update

from .audit import record_event
from .models import Launch


def rename_user(db, request, user, *, first_name, last_name, full_name):
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
```

- [ ] **Step 5: Вызвать из обоих путей входа**

`auth.py`, callback: убрать `full_name` из `set_` upsert (оставить в `values` для первой вставки) и добавить `first_name`/`last_name` в `values`; после получения `row`:

```python
    user = db.get(User, row.id)
    rename_user(db, request, user, first_name=identity.given_name or user.first_name,
                last_name=identity.family_name or user.last_name, full_name=identity.full_name)
```

`or user.first_name`: токен без `given_name` (учётная запись без заполненного имени) не должен стирать сохранённое имя.

Upsert-вставка нового пользователя уже пишет `full_name=identity.full_name`, поэтому для нового пользователя `rename_user` видит совпадение и не пишет событие. Для существующего пользователя `set_` больше не трогает `full_name`, и сравнение идёт со старым значением.

`_revalidate`: заменить `user.full_name = identity.full_name` на

```python
    rename_user(db, request, user, first_name=identity.given_name or user.first_name,
                last_name=identity.family_name or user.last_name, full_name=identity.full_name)
```

Импорт в `auth.py`: `from .owner_links import rename_user`. Проверить отсутствие циклического импорта (`owner_links` → `audit` → `models`; `audit` не импортирует `auth`). Если `audit.py` импортирует `auth` — перенести импорт внутрь функции `rename_user`.

- [ ] **Step 6: Запустить тесты**

Run: `uv run pytest tests/test_rename_cascade.py tests/test_auth.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/owner_links.py backend/app/oidc.py backend/app/auth.py backend/tests/fake_keycloak.py backend/tests/test_rename_cascade.py
git commit -m "feat: carry user renames onto linked interactions on login and session refresh

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: API профиля без подтверждения телефона

**Files:**
- Rewrite: `backend/app/profile_routes.py`
- Modify: `backend/app/auth.py` (`CurrentUser`, `me`)
- Delete: `backend/tests/test_phone_verification.py`
- Test: `backend/tests/test_profile_routes.py`

**Interfaces:**
- Consumes: `KeycloakAdminClient.update_user_names` (Task 3), `rename_user`, `normalize_name` (Tasks 2, 4).
- Produces: `GET /api/v1/profile` → `ProfileOut`; `PATCH /api/v1/profile` (`ProfilePatch`, все поля необязательны) → `ProfileOut`. `ProfileOut = {id, email, first_name, last_name, full_name, phone, timezone, messengers: [{service, handle}], email_sender_identity_id: int | None}`. `/auth/me` → `user` получает `first_name`, `last_name`, `timezone`, `messengers`, без `phone_verified_at`. Task 6 добавляет в `ProfilePatch` поле `email_sender_identity_id`.

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_profile_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import Launch, User
from app.plan_routes import resolve_assignee
from fake_keycloak import ADMIN_BASE_URL, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET
from helpers import database, login, make_settings
from test_reports import create_launch, create_university

PROFILE = '/api/v1/profile'


@pytest.fixture
def kc_client(database_url, keycloak):
    app = create_app(make_settings(database_url, keycloak_admin_client_id=ADMIN_CLIENT_ID,
                                   keycloak_admin_client_secret=ADMIN_CLIENT_SECRET,
                                   keycloak_admin_base_url=ADMIN_BASE_URL), http_client=keycloak.http_client())
    with TestClient(app) as test_client:
        yield test_client


def _login_irina(client, keycloak):
    keycloak.add_admin_user(id='kc-irina', email='irina@x.test', username='irina', roles=['crm-admin'],
                            first_name='Ирина', last_name='Петрова')
    return login(client, keycloak, roles=('crm-admin',), subject='kc-irina', name='Ирина Петрова', email='irina@x.test')


def test_get_profile_defaults(kc_client, keycloak):
    _login_irina(kc_client, keycloak)
    body = kc_client.get(PROFILE).json()
    assert body['full_name'] == 'Ирина Петрова' and body['timezone'] == 'Europe/Moscow'
    assert body['messengers'] == [] and body['email_sender_identity_id'] is None
    # Names not yet mirrored locally fall back to splitting full_name once.
    assert (body['first_name'], body['last_name']) == ('Ирина', 'Петрова')


def test_patch_non_name_fields_without_keycloak_admin(client, keycloak):
    login(client, keycloak)
    response = client.patch(PROFILE, json={
        'phone': '8 (999) 123-45-67', 'timezone': 'Asia/Yekaterinburg',
        'messengers': [{'service': 'telegram', 'handle': '@anna_demo'}, {'service': 'whatsapp', 'handle': '+79991234567'}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['phone'] == '+79991234567' and body['timezone'] == 'Asia/Yekaterinburg'
    assert body['messengers'][0] == {'service': 'telegram', 'handle': 'anna_demo'}


@pytest.mark.parametrize('payload,field', [
    ({'timezone': 'Mars/Olympus'}, 'timezone'),
    ({'timezone': ''}, 'timezone'),
    ({'phone': 'not a phone'}, 'phone'),
    ({'messengers': [{'service': 'icq', 'handle': 'x'}]}, 'messengers.0.service'),
    ({'messengers': [{'service': 'telegram', 'handle': 'x'}] * 11}, 'messengers'),
    ({'first_name': '   '}, 'first_name'),
])
def test_patch_rejects_invalid_values(client, keycloak, payload, field):
    login(client, keycloak)
    response = client.patch(PROFILE, json=payload)
    assert response.status_code == 422
    assert any(d['field'] == field for d in response.json()['details'])


def test_empty_phone_clears_it(client, keycloak):
    login(client, keycloak)
    client.patch(PROFILE, json={'phone': '+79991234567'})
    assert client.patch(PROFILE, json={'phone': ''}).json()['phone'] == ''


def test_rename_writes_keycloak_then_cascades(kc_client, keycloak, database_url):
    me = _login_irina(kc_client, keycloak)
    university = create_university(kc_client, 'Вуз профиля')
    launch_id = create_launch(kc_client, university['id'], owner='Ирина Петрова')['id']
    response = kc_client.patch(PROFILE, json={'first_name': 'Ирина', 'last_name': 'Смирнова'})
    assert response.status_code == 200, response.text
    assert response.json()['full_name'] == 'Ирина Смирнова'
    assert keycloak.admin_users['kc-irina']['lastName'] == 'Смирнова'
    with database(database_url) as db:
        launch = db.get(Launch, launch_id)
        assert launch.owner == 'Ирина Смирнова'
        assert resolve_assignee(db, {'assignee_rule': 'interaction_owner'}, university['id'], launch, None) == (me['user']['id'], None)
    options = kc_client.get('/api/v1/reports/options').json()['owners']
    assert 'Ирина Смирнова' in options and 'Ирина Петрова' not in options
    report = kc_client.get('/api/v1/reports/interactions', params={'owner': 'Ирина Смирнова'})
    assert report.status_code == 200, report.text
    assert report.json()['total'] == 1


def test_new_launch_with_new_name_links(kc_client, keycloak):
    me = _login_irina(kc_client, keycloak)
    kc_client.patch(PROFILE, json={'first_name': 'Ирина', 'last_name': 'Смирнова'})
    university = create_university(kc_client, 'Вуз после переименования')
    assert create_launch(kc_client, university['id'], owner='Ирина Смирнова')['owner_user_id'] == me['user']['id']


def test_keycloak_failure_changes_nothing(kc_client, keycloak, database_url):
    _login_irina(kc_client, keycloak)
    university = create_university(kc_client, 'Вуз отказа')
    launch_id = create_launch(kc_client, university['id'], owner='Ирина Петрова')['id']
    keycloak.unavailable = True
    response = kc_client.patch(PROFILE, json={'first_name': 'Ирина', 'last_name': 'Смирнова', 'timezone': 'Asia/Omsk'})
    keycloak.unavailable = False
    assert response.status_code == 503
    with database(database_url) as db:
        user = db.scalar(select(User).where(User.keycloak_sub == 'kc-irina'))
        assert user.full_name == 'Ирина Петрова' and user.timezone == 'Europe/Moscow'
        assert db.get(Launch, launch_id).owner == 'Ирина Петрова'


def test_rename_without_keycloak_admin_is_unavailable(client, keycloak):
    login(client, keycloak)
    assert client.patch(PROFILE, json={'first_name': 'Новое', 'last_name': 'Имя'}).status_code == 503


def test_duplicate_name_of_another_active_user_is_rejected(kc_client, keycloak, database_url):
    with database(database_url) as db:
        db.add(User(keycloak_sub='kc-other', email='o@x.test', full_name='Анна Смирнова', roles=['crm-user'], is_active=True))
        db.commit()
    _login_irina(kc_client, keycloak)
    response = kc_client.patch(PROFILE, json={'first_name': 'анна', 'last_name': 'смирнова '})
    assert response.status_code == 422
    assert response.json()['details'][0]['field'] == 'first_name'
    assert keycloak.admin_users['kc-irina']['lastName'] == 'Петрова'


def test_own_name_in_other_case_is_not_a_conflict(kc_client, keycloak):
    _login_irina(kc_client, keycloak)
    response = kc_client.patch(PROFILE, json={'first_name': 'ирина', 'last_name': 'петрова'})
    assert response.status_code == 200, response.text


def test_phone_verification_endpoints_are_gone(client, keycloak):
    login(client, keycloak)
    assert client.post(f'{PROFILE}/phone', json={'phone': '+79991234567'}).status_code in (404, 405)


def test_me_exposes_profile_fields(client, keycloak):
    login(client, keycloak)
    user = client.get('/api/v1/auth/me').json()['user']
    assert {'first_name', 'last_name', 'timezone', 'messengers'} <= user.keys()
    assert 'phone_verified_at' not in user
```

Перед запуском свериться с `tests/test_reports.py`, как передаётся фильтр `owner` в `/reports/interactions` (список параметров `owner=...` или JSON) и как называется поле итога (`total`), и привести последние три строки `test_rename_writes_keycloak_then_cascades` к фактическому контракту.

- [ ] **Step 2: Запустить — должен упасть**

Run: `uv run pytest tests/test_profile_routes.py -v`
Expected: FAIL — `GET /api/v1/profile` отвечает 404/405.

- [ ] **Step 3: Переписать `profile_routes.py`**

```python
"""The signed-in user's own profile (Настройки → Личный профиль; spec 2026-09-27, section 1).

Names live in Keycloak and are mirrored here; phone, time zone and messenger handles are CRM-only.
SMS phone verification (D-155–D-157) was withdrawn: phone is a plain, normalized field.
"""
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .keycloak_admin import KeycloakAdminError
from .models import User
from .owner_links import normalize_name, rename_user
from .phone import PhoneFormatError, normalize_phone

router = APIRouter(prefix='/api/v1/profile', tags=['Профиль'])
any_role = require_roles(*ALL_ROLES)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
MESSENGER_SERVICES = ('telegram', 'whatsapp', 'viber', 'vk', 'max', 'other')
NAME_TAKEN = 'Такое имя уже есть у другого пользователя CRM'
KEYCLOAK_DOWN = 'Не удалось сохранить имя: сервис учётных записей недоступен, попробуйте позже'


class Messenger(BaseModel):
    service: Literal['telegram', 'whatsapp', 'viber', 'vk', 'max', 'other']
    handle: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=101)]

    @field_validator('handle')
    @classmethod
    def strip_at(cls, value):
        value = value.removeprefix('@').strip()
        if not value or len(value) > 100:
            raise ValueError('Укажите имя пользователя длиной от 1 до 100 символов')
        return value


class ProfilePatch(BaseModel):
    first_name: Name | None = None
    last_name: Name | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    timezone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None = None
    messengers: list[Messenger] | None = Field(default=None, max_length=10)

    @field_validator('timezone')
    @classmethod
    def known_timezone(cls, value):
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Неизвестный часовой пояс')
        return value


class ProfileOut(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    full_name: str
    phone: str
    timezone: str
    messengers: list[Messenger]
    email_sender_identity_id: int | None


def profile_out(user):
    first, last = user.first_name, user.last_name
    if not first and not last:
        first, _, last = user.full_name.partition(' ')
    return ProfileOut(
        id=user.id, email=user.email, first_name=first, last_name=last, full_name=user.full_name,
        phone=user.phone, timezone=user.timezone, messengers=user.messengers or [],
        email_sender_identity_id=user.email_sender_identity_id,
    )


def _field_error(field, message):
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': field, 'message': message, 'type': 'value_error'}])


@router.get('', response_model=ProfileOut, summary='Мой профиль')
def get_profile(auth: AuthContext = Depends(any_role)):
    return profile_out(auth.user)


@router.patch('', response_model=ProfileOut, summary='Изменить мой профиль')
def update_profile(data: ProfilePatch, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    user = auth.user
    changed = []
    phone = None
    if data.phone is not None:
        try:
            phone = normalize_phone(data.phone) if data.phone else ''
        except PhoneFormatError as error:
            raise _field_error('phone', str(error)) from error

    current = profile_out(user)
    first = data.first_name if data.first_name is not None else current.first_name
    last = data.last_name if data.last_name is not None else current.last_name
    full_name = f'{first} {last}'.strip()
    name_changed = (data.first_name is not None or data.last_name is not None) and full_name != user.full_name
    if name_changed:
        taken = db.scalar(select(User.id).where(
            User.id != user.id, User.is_active.is_(True),
            func.lower(func.regexp_replace(func.btrim(User.full_name), r'\s+', ' ', 'g')) == normalize_name(full_name),
        ).limit(1))
        if taken is not None:
            raise _field_error('first_name', NAME_TAKEN)
        keycloak_admin = request.app.state.keycloak_admin
        if not keycloak_admin.is_configured():
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, KEYCLOAK_DOWN)
        try:
            keycloak_admin.update_user_names(user.keycloak_sub, first_name=first, last_name=last)
        except KeycloakAdminError as error:
            db.rollback()
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, KEYCLOAK_DOWN) from error
        rename_user(db, request, user, first_name=first, last_name=last, full_name=full_name)
        changed.append('name')
    elif data.first_name is not None or data.last_name is not None:
        user.first_name, user.last_name = first, last

    if phone is not None and phone != user.phone:
        user.phone = phone
        changed.append('phone')
    if data.timezone is not None and data.timezone != user.timezone:
        user.timezone = data.timezone
        changed.append('timezone')
    if data.messengers is not None:
        messengers = [m.model_dump() for m in data.messengers]
        if messengers != (user.messengers or []):
            user.messengers = messengers
            changed.append('messengers')
    if changed:
        # Field names only: phone numbers and messenger handles stay out of the audit log.
        record_event(db, request, user, 'profile.update', entity_type='user', entity_id=user.id,
                     summary='Изменён личный профиль', payload={'fields': changed})
    db.commit()
    return profile_out(user)
```

Проверить, что поле ошибки для вложенного мессенджера приходит как `messengers.0.service` (обработчик ошибок валидации в `errors.py` склеивает `loc` через точку — см. `legacyDetails` на фронте и серверный обработчик). Если формат иной — поправить ожидание в параметризованном тесте, не обработчик.

- [ ] **Step 4: `/auth/me`**

В `auth.py` `CurrentUser` заменить поля телефона:

```python
    first_name: str
    last_name: str
    phone: str
    timezone: str
    messengers: list[dict]
```

и в `me()`:

```python
            phone=auth.user.phone, first_name=auth.user.first_name, last_name=auth.user.last_name,
            timezone=auth.user.timezone, messengers=auth.user.messengers or [],
```

- [ ] **Step 5: Удалить старые тесты SMS и запустить**

```bash
git rm backend/tests/test_phone_verification.py
uv run pytest tests/test_profile_routes.py tests/test_auth.py -v && uv run pytest -q
```

Expected: PASS; весь набор зелёный, включая тесты импорта, контактов, вендоров и слушателей без изменений. Если `grep -rn "phone_verified_at\|profile/phone" backend` находит другие использования (кроме `models.py` и миграций) — убрать их.

- [ ] **Step 6: Commit**

```bash
git add backend/app/profile_routes.py backend/app/auth.py backend/tests/test_profile_routes.py
git commit -m "feat: editable profile with Keycloak names, plain phone, time zone and messengers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Проверка адреса перед отправкой и выбор в профиле

**Files:**
- Create: `backend/app/sender_addresses.py`
- Modify: `backend/app/email_routes.py` (`test_send`, ~стр. 88–120)
- Modify: `backend/app/profile_routes.py` (`ProfilePatch`, `update_profile`)
- Modify: `backend/tests/test_email_senders.py` (`test_test_send_uses_the_selected_sender_identity_as_the_from_address`)
- Test: `backend/tests/test_sender_guard.py`

**Interfaces:**
- Produces: `SENDER_UNAVAILABLE: str`; `usable_sender(db, user, identity_id: int) -> EmailSenderIdentity` (свежее чтение `FOR SHARE`; `AppError(CONFLICT, SENDER_UNAVAILABLE)` при нарушении). `is_usable(identity, user) -> bool`. `ProfilePatch.email_sender_identity_id: int | None` — `0` снимает выбор, число выбирает адрес. Task 7 использует `is_usable` для поля `usable` в ответах списка.

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_sender_guard.py`:

```python
import pytest
from sqlalchemy import update

from app.models import EmailSenderIdentity, User
from helpers import database, login

PROFILE = '/api/v1/profile'


def _sender(database_url, address, *, owner=None, status='active', is_active=True):
    with database(database_url) as db:
        row = EmailSenderIdentity(email_address=address, display_name=address, owner_user_id=owner,
                                  status=status, is_active=is_active)
        db.add(row)
        db.commit()
        return row.id


def _select(database_url, user_id, sender_id):
    with database(database_url) as db:
        db.execute(update(User).where(User.id == user_id).values(email_sender_identity_id=sender_id))
        db.commit()


def test_select_shared_active_sender(client, keycloak, database_url):
    login(client, keycloak)
    sender_id = _sender(database_url, 'office@uni.test')
    response = client.patch(PROFILE, json={'email_sender_identity_id': sender_id})
    assert response.status_code == 200 and response.json()['email_sender_identity_id'] == sender_id
    assert client.patch(PROFILE, json={'email_sender_identity_id': 0}).json()['email_sender_identity_id'] is None


@pytest.mark.parametrize('kwargs', [
    {'status': 'pending_approval'}, {'status': 'awaiting_confirmation'}, {'status': 'rejected'},
    {'is_active': False}, {'owner': 'other'},
])
def test_select_rejects_unusable_sender(client, keycloak, database_url, kwargs):
    login(client, keycloak)
    if kwargs.get('owner') == 'other':
        with database(database_url) as db:
            other = User(keycloak_sub='kc-o', email='o@x.test', full_name='Другой', roles=['crm-user'])
            db.add(other)
            db.commit()
            kwargs = {'owner': other.id}
    sender_id = _sender(database_url, 'x@uni.test', **kwargs)
    response = client.patch(PROFILE, json={'email_sender_identity_id': sender_id})
    assert response.status_code == 409
    assert response.json()['message'] == 'Выбранный адрес отправителя недоступен — выберите другой в профиле'


def test_test_send_refuses_a_sender_deactivated_after_selection(client, keycloak, database_url, app):
    sent = []
    app.state.email_sender = lambda *args, **kwargs: sent.append((args, kwargs))
    me = login(client, keycloak)
    sender_id = _sender(database_url, 'office@uni.test')
    client.patch(PROFILE, json={'email_sender_identity_id': sender_id})
    with database(database_url) as db:
        db.execute(update(EmailSenderIdentity).where(EmailSenderIdentity.id == sender_id).values(is_active=False))
        db.commit()
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 409 and sent == []
    assert client.get(PROFILE).json()['email_sender_identity_id'] == sender_id  # selection kept, shown as unavailable


def test_test_send_refuses_someone_elses_personal_sender(client, keycloak, database_url, app):
    sent = []
    app.state.email_sender = lambda *args, **kwargs: sent.append(kwargs)
    me = login(client, keycloak)
    with database(database_url) as db:
        other = User(keycloak_sub='kc-o', email='o@x.test', full_name='Другой', roles=['crm-user'])
        db.add(other)
        db.commit()
        other_id = other.id
    _select(database_url, me['user']['id'], _sender(database_url, 'p@uni.test', owner=other_id))
    assert client.post('/api/v1/email-senders/test').status_code == 409 and sent == []


def test_test_send_uses_own_active_personal_sender(client, keycloak, database_url, app):
    sent = []
    app.state.email_sender = lambda *args, **kwargs: sent.append(kwargs)
    me = login(client, keycloak)
    _select(database_url, me['user']['id'], _sender(database_url, 'mine@uni.test', owner=me['user']['id']))
    assert client.post('/api/v1/email-senders/test').status_code == 200
    assert sent == [{'from_address': 'mine@uni.test'}]
```

Ответ ошибки должен содержать ключ `message` — свериться с форматом `AppError` в `errors.py` (соседние тесты, например в `test_email_senders.py`, показывают, как читается текст ошибки) и при необходимости заменить `response.json()['message']` на фактический ключ.

- [ ] **Step 2: Запустить — должен упасть**

Run: `uv run pytest tests/test_sender_guard.py -v`
Expected: FAIL — `email_sender_identity_id` игнорируется, `test_send` отправляет с деактивированного адреса.

- [ ] **Step 3: `sender_addresses.py`**

```python
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
```

- [ ] **Step 4: Подключить к `test_send` и профилю**

`email_routes.py` — в `test_send` заменить строку с `from_identity = db.get(...)` на:

```python
    from_identity = usable_sender(db, auth.user, auth.user.email_sender_identity_id) if auth.user.email_sender_identity_id else None
```

Вызов остаётся после проверки лимита и непосредственно перед `sender(...)`: перенести проверку кулдауна выше вычисления `from_identity`, чтобы между `usable_sender` и отправкой не было других действий. Импорт `from .sender_addresses import usable_sender`.

`profile_routes.py` — в `ProfilePatch`:

```python
    email_sender_identity_id: int | None = Field(default=None, ge=0)
```

и в `update_profile` перед блоком `if changed:`:

```python
    if data.email_sender_identity_id is not None:
        new_id = usable_sender(db, user, data.email_sender_identity_id).id if data.email_sender_identity_id else None
        if new_id != user.email_sender_identity_id:
            user.email_sender_identity_id = new_id
            changed.append('email_sender')
```

Импорт `from .sender_addresses import usable_sender`. Проверка адреса выполняется до вызова Keycloak только если перенести блок выше `name_changed`; перенести его сразу после разбора телефона, чтобы отказ по адресу не оставлял изменённого имени в Keycloak.

- [ ] **Step 5: Обновить существующий тест выбора адреса**

В `tests/test_email_senders.py::test_test_send_uses_the_selected_sender_identity_as_the_from_address` адрес создаётся через `POST /email-senders` — после Task 7 он будет `awaiting_confirmation`. Уже сейчас заменить в тесте выбор через `update(User)` на прямое создание активной строки в БД (как `_sender` выше), чтобы тест не зависел от процесса подтверждения.

- [ ] **Step 6: Запустить тесты**

Run: `uv run pytest tests/test_sender_guard.py tests/test_email_senders.py tests/test_profile_routes.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/sender_addresses.py backend/app/email_routes.py backend/app/profile_routes.py backend/tests/test_sender_guard.py backend/tests/test_email_senders.py
git commit -m "fix: re-check sender owner and status right before every send and on selection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Заявки, одобрение и подтверждение адресов

**Files:**
- Modify: `backend/app/sender_addresses.py` (токены, письмо подтверждения)
- Modify: `backend/app/email_routes.py` (новые эндпоинты; `list_senders`, `create_sender`)
- Modify: `backend/tests/test_email_senders.py` (`test_supervisor_can_create_and_it_is_immediately_approved`, `test_recreating_a_deactivated_sender_reactivates_the_same_row`)
- Test: `backend/tests/test_sender_requests.py`

**Interfaces:**
- Consumes: `usable_sender`, `is_usable` (Task 6).
- Produces (все под `/api/v1/email-senders`):
  - `GET ''` — активные общие + все собственные адреса вызывающего; элементы `SenderOut = {id, email_address, display_name, is_active, status, is_shared, rejection_reason, usable}`.
  - `POST /requests` `{email_address, display_name}` → 201 `SenderOut` (личная заявка).
  - `DELETE /requests/{id}` → 204 (отзыв своей открытой заявки).
  - `GET /queue` → `list[QueueItemOut]` — `SenderOut` + `requested_by: str`, `requested_at`; только `crm-supervisor`/`crm-admin`; статусы `pending_approval` и `awaiting_confirmation`.
  - `POST /{id}/approve` → `{delivered: bool, message: str}`.
  - `POST /{id}/reject` `{reason}` → 204.
  - `POST /{id}/resend` → `{delivered, message}`.
  - `POST /confirm` `{token}` → `{email_address}`; без сессии.
  - `POST ''` (существующий, руководитель/админ) — общий адрес в `awaiting_confirmation` + письмо; ответ `SenderOut` (201).
  - `sender_addresses.issue_confirmation(db, request, identity) -> tuple[bool, str]` — создаёт токен, отправляет письмо, возвращает `(delivered, message)`.

- [ ] **Step 1: Написать падающие тесты**

`backend/tests/test_sender_requests.py`:

```python
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models import AuditEvent, EmailSenderIdentity, User, utcnow
from helpers import database, login

BASE = '/api/v1/email-senders'


def _capture(app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body, **kwargs: sent.append({'to': to, 'body': body, **kwargs})
    return sent


def _token(sent):
    body = sent[-1]['body']
    return body.split('token=')[1].split()[0]


def _as(client, keycloak, role, subject, name):
    client.cookies.clear()
    client.headers.pop('X-CSRF-Token', None)
    return login(client, keycloak, roles=(role,), subject=subject, name=name, email=f'{subject}@x.test')


def _request(client, address='anna@uni.test'):
    response = client.post(f'{BASE}/requests', json={'email_address': address, 'display_name': 'Анна'})
    assert response.status_code == 201, response.text
    return response.json()


def test_full_request_flow_selects_the_confirmed_address(client, keycloak, app, database_url):
    sent = _capture(app)
    anna = _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    assert created['status'] == 'pending_approval' and created['usable'] is False

    _as(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель')
    queue = client.get(f'{BASE}/queue').json()
    assert [q['id'] for q in queue] == [created['id']] and queue[0]['requested_by'] == 'Анна Петрова'
    approved = client.post(f"{BASE}/{created['id']}/approve")
    assert approved.status_code == 200 and approved.json()['delivered'] is True
    assert sent[-1]['to'] == 'anna@uni.test' and '/confirm-sender?token=' in sent[-1]['body']

    client.cookies.clear()
    client.headers.pop('X-CSRF-Token', None)
    confirmed = client.post(f'{BASE}/confirm', json={'token': _token(sent)})
    assert confirmed.status_code == 200, confirmed.text
    with database(database_url) as db:
        row = db.get(EmailSenderIdentity, created['id'])
        assert row.status == 'active' and row.confirmation_token_hash is None
        assert db.get(User, anna['user']['id']).email_sender_identity_id == created['id']
        actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_type == 'email_sender_identity')))
        assert {'email_sender.request', 'email_sender.approve', 'email_sender.confirm'} <= actions


def test_get_does_not_confirm_and_token_is_single_use(client, keycloak, app):
    sent = _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    client.post(f"{BASE}/{created['id']}/approve")
    token = _token(sent)
    assert client.get(f'{BASE}/confirm', params={'token': token}).status_code in (404, 405)
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 200
    second = client.post(f'{BASE}/confirm', json={'token': token})
    assert second.status_code == 409 and 'недействительна' in second.text


def test_expired_wrong_and_withdrawn_tokens_are_rejected(client, keycloak, app, database_url):
    sent = _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    client.post(f"{BASE}/{created['id']}/approve")
    token = _token(sent)
    assert client.post(f'{BASE}/confirm', json={'token': 'wrong'}).status_code == 409
    with database(database_url) as db:
        db.execute(update(EmailSenderIdentity).values(confirmation_expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 409


def test_link_after_deactivation_does_not_activate(client, keycloak, app, database_url):
    sent = _capture(app)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    shared = client.post(BASE, json={'email_address': 'office@uni.test', 'display_name': 'Офис'}).json()
    assert shared['status'] == 'awaiting_confirmation' and shared['is_shared'] is True
    token = _token(sent)
    assert client.delete(f"{BASE}/{shared['id']}").status_code == 204
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 409
    with database(database_url) as db:
        assert db.get(EmailSenderIdentity, shared['id']).status == 'awaiting_confirmation'


def test_withdrawn_request_link_is_invalid(client, keycloak, app):
    sent = _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    client.post(f"{BASE}/{created['id']}/approve")
    token = _token(sent)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.delete(f"{BASE}/requests/{created['id']}").status_code == 204
    assert client.post(f'{BASE}/confirm', json={'token': token}).status_code == 409


def test_self_approval_is_forbidden(client, keycloak, app):
    _capture(app)
    _as(client, keycloak, 'crm-supervisor', 'kc-boss', 'Руководитель')
    created = _request(client, 'boss@uni.test')
    assert client.post(f"{BASE}/{created['id']}/approve").status_code == 403


def test_one_open_request_per_user_and_taken_address(client, keycloak, app):
    _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    _request(client)
    second = client.post(f'{BASE}/requests', json={'email_address': 'other@uni.test', 'display_name': 'Анна'})
    assert second.status_code == 409
    _as(client, keycloak, 'crm-user', 'kc-ivan', 'Иван Иванов')
    taken = client.post(f'{BASE}/requests', json={'email_address': 'anna@uni.test', 'display_name': 'Иван'})
    assert taken.status_code == 422


def test_reject_with_reason_and_rerequest_reuses_row(client, keycloak, app):
    _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    assert client.post(f"{BASE}/{created['id']}/reject", json={'reason': 'Не наш домен'}).status_code == 204
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    mine = [s for s in client.get(BASE).json() if s['id'] == created['id']][0]
    assert mine['status'] == 'rejected' and mine['rejection_reason'] == 'Не наш домен'
    again = _request(client)
    assert again['id'] == created['id'] and again['status'] == 'pending_approval' and again['rejection_reason'] == ''


def test_queue_is_for_supervisor_and_admin_only(client, keycloak):
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    assert client.get(f'{BASE}/queue').status_code == 403


def test_resend_cooldown_and_new_link_invalidates_old(client, keycloak, app, database_url):
    sent = _capture(app)
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    client.post(f"{BASE}/{created['id']}/approve")
    first = _token(sent)
    assert client.post(f"{BASE}/{created['id']}/resend").status_code == 429
    with database(database_url) as db:
        db.execute(update(EmailSenderIdentity).values(confirmation_sent_at=utcnow() - timedelta(seconds=61)))
        db.commit()
    assert client.post(f"{BASE}/{created['id']}/resend").status_code == 200
    second = _token(sent)
    assert client.post(f'{BASE}/confirm', json={'token': first}).status_code == 409
    assert client.post(f'{BASE}/confirm', json={'token': second}).status_code == 200


def test_approve_without_provider_says_logged_only(client, keycloak):
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    created = _request(client)
    _as(client, keycloak, 'crm-admin', 'kc-adm', 'Админ')
    body = client.post(f"{BASE}/{created['id']}/approve").json()
    assert body['delivered'] is False and 'журнал' in body['message']


def test_list_shows_shared_active_and_own_rows_only(client, keycloak, app, database_url):
    _capture(app)
    with database(database_url) as db:
        db.add(EmailSenderIdentity(email_address='office@uni.test', display_name='Офис', status='active'))
        db.add(EmailSenderIdentity(email_address='new@uni.test', display_name='Новый', status='awaiting_confirmation'))
        db.commit()
    _as(client, keycloak, 'crm-user', 'kc-ivan', 'Иван Иванов')
    _request(client, 'ivan@uni.test')
    _as(client, keycloak, 'crm-user', 'kc-anna', 'Анна Петрова')
    _request(client, 'anna@uni.test')
    addresses = {s['email_address'] for s in client.get(BASE).json()}
    assert addresses == {'office@uni.test', 'anna@uni.test'}
```

`test_approve_without_provider_says_logged_only` использует фикстуру `client` без подменённого отправителя — значит, `app.state.email_sender` там равен `send_email`, а `email_provider_url` пуст. Сверить с фикстурой `app` в `conftest.py`: `create_app(..., email_sender=None)` ставит `send_email`.

Если ошибки лимита используют код, отличный от 429 (`ErrorCode.RATE_LIMITED`), взять код из существующего `test_test_send_is_rate_limited_to_once_per_minute`.

- [ ] **Step 2: Запустить — должен упасть**

Run: `uv run pytest tests/test_sender_requests.py -v`
Expected: FAIL — `POST /api/v1/email-senders/requests` 404/405.

- [ ] **Step 3: Токены и письмо в `sender_addresses.py`**

Добавить:

```python
import secrets
from datetime import timedelta

from .email import EmailSendError, send_email
from .models import utcnow
from .security import token_hash

CONFIRMATION_TTL = timedelta(hours=48)
RESEND_COOLDOWN_SECONDS = 60
INVALID_LINK = 'Ссылка недействительна или устарела'


def _sender_fn(request):
    return getattr(request.app.state, 'email_sender', None) or send_email


def issue_confirmation(db, request, identity):
    """New single-use link (replacing any previous one) mailed to the address itself, from the
    system sender. Returns (delivered, message) with the project's honesty rule for unconfigured mail."""
    settings = request.app.state.settings
    token = secrets.token_urlsafe(32)
    now = utcnow()
    identity.confirmation_token_hash = token_hash(token)
    identity.confirmation_expires_at = now + CONFIRMATION_TTL
    identity.confirmation_sent_at = now
    link = f'{settings.public_base_url}/confirm-sender?token={token}'
    body = (
        f'Этот адрес добавляют как адрес отправителя писем UniCRM («{identity.display_name}»).\n'
        f'Чтобы подтвердить, откройте ссылку и нажмите «Подтвердить»: {link}\n'
        'Ссылка действует 48 часов. Если вы не ожидали это письмо, просто проигнорируйте его.'
    )
    sender = _sender_fn(request)
    try:
        sender(settings, identity.email_address, 'Подтвердите адрес отправителя UniCRM', body,
               from_address=settings.email_sender_address or None)
    except EmailSendError as error:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось отправить письмо подтверждения, попробуйте позже') from error
    if settings.email_provider_url or sender is not send_email:
        return True, f'Письмо подтверждения отправлено на {identity.email_address}.'
    return False, 'Почтовый провайдер не настроен: письмо подтверждения записано только в журнал сервера.'
```

Пробел после токена в теле письма обязателен — тесты вырезают токен до первого пробельного символа.

- [ ] **Step 4: Эндпоинты в `email_routes.py`**

Заменить `SenderOut`/`sender_out`/`list_senders`/`create_sender` и добавить новые обработчики:

```python
from datetime import datetime

from sqlalchemy import or_

from .models import User
from .sender_addresses import (
    INVALID_LINK, RESEND_COOLDOWN_SECONDS, is_usable, issue_confirmation, usable_sender,
)

OPEN_STATUSES = ('pending_approval', 'awaiting_confirmation')
Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class SenderOut(BaseModel):
    id: int
    email_address: str
    display_name: str
    is_active: bool
    status: str
    is_shared: bool
    rejection_reason: str
    usable: bool


class QueueItemOut(SenderOut):
    requested_by: str
    requested_at: datetime | None


class RejectIn(BaseModel):
    reason: Reason = ''


class ConfirmIn(BaseModel):
    token: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class DeliveryOut(BaseModel):
    delivered: bool
    message: str


def sender_out(row, user=None):
    return SenderOut(
        id=row.id, email_address=row.email_address, display_name=row.display_name, is_active=row.is_active,
        status=row.status, is_shared=row.owner_user_id is None, rejection_reason=row.rejection_reason,
        usable=is_usable(row, user) if user is not None else (row.is_active and row.status == 'active'),
    )


def _event(db, request, actor, action, row, summary):
    record_event(db, request, actor, action, entity_type='email_sender_identity', entity_id=row.id,
                 summary=summary, payload={'email_address': row.email_address})


def _address_taken(db, address, *, except_id=None):
    row = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.email_address == address))
    if row is None or row.id == except_id:
        return None, row
    if row.status == 'rejected' or (not row.is_active and row.owner_user_id is None):
        return None, row
    return row, row


@router.get('', response_model=list[SenderOut], summary='Доступные мне адреса отправителей')
def list_senders(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailSenderIdentity).where(or_(
        EmailSenderIdentity.owner_user_id == auth.user.id,
        (EmailSenderIdentity.owner_user_id.is_(None)) & EmailSenderIdentity.is_active.is_(True)
        & (EmailSenderIdentity.status == 'active'),
    )).order_by(EmailSenderIdentity.display_name)).all()
    return [sender_out(r, auth.user) for r in rows]


@router.post('/requests', response_model=SenderOut, status_code=201, summary='Заявка на личный адрес отправителя')
def request_sender(data: SenderIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    open_request = db.scalar(select(EmailSenderIdentity.id).where(
        EmailSenderIdentity.owner_user_id == auth.user.id, EmailSenderIdentity.status.in_(OPEN_STATUSES),
        EmailSenderIdentity.is_active.is_(True)))
    if open_request is not None:
        raise AppError(ErrorCode.CONFLICT, 'У вас уже есть открытая заявка — дождитесь решения или отзовите её')
    taken, existing = _address_taken(db, data.email_address)
    if taken is not None and taken.owner_user_id != auth.user.id:
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'email_address', 'message': 'Этот адрес уже используется', 'type': 'value_error'}])
    row = existing if existing is not None else EmailSenderIdentity(email_address=data.email_address)
    row.display_name = data.display_name
    row.owner_user_id = auth.user.id
    row.status = 'pending_approval'
    row.is_active = True
    row.rejection_reason = ''
    row.requested_by_user_id = auth.user.id
    row.requested_at = utcnow()
    row.created_by_user_id = row.created_by_user_id or auth.user.id
    row.confirmation_token_hash = None
    if existing is None:
        db.add(row)
    db.flush()
    _event(db, request, auth.user, 'email_sender.request', row, f'Заявка на адрес отправителя {row.email_address}')
    db.commit()
    return sender_out(row, auth.user)


@router.delete('/requests/{sender_id}', status_code=204, summary='Отозвать свою заявку')
def withdraw_request(sender_id: int, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    row = db.get(EmailSenderIdentity, sender_id)
    if row is None or row.owner_user_id != auth.user.id or row.status not in OPEN_STATUSES:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    row.status = 'rejected'
    row.rejection_reason = 'Отозвана заявителем'
    row.confirmation_token_hash = None
    _event(db, request, auth.user, 'email_sender.withdraw', row, f'Заявка на адрес {row.email_address} отозвана')
    db.commit()


@router.get('/queue', response_model=list[QueueItemOut], summary='Заявки на адреса отправителей', dependencies=[Depends(sender_manager)])
def queue(db: Session = Depends(get_db)):
    rows = db.execute(
        select(EmailSenderIdentity, User.full_name)
        .outerjoin(User, User.id == EmailSenderIdentity.requested_by_user_id)
        .where(EmailSenderIdentity.status.in_(OPEN_STATUSES), EmailSenderIdentity.is_active.is_(True))
        .order_by(EmailSenderIdentity.requested_at.nullslast(), EmailSenderIdentity.id)
    ).all()
    return [QueueItemOut(**sender_out(r).model_dump(), requested_by=name or '', requested_at=r.requested_at) for r, name in rows]


def _open_row(db, sender_id, status):
    row = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.id == sender_id).with_for_update())
    if row is None or row.status != status or not row.is_active:
        raise AppError(ErrorCode.CONFLICT, 'Заявка уже обработана или недоступна')
    return row


@router.post('/{sender_id}/approve', response_model=DeliveryOut, summary='Одобрить заявку и отправить письмо подтверждения')
def approve(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = _open_row(db, sender_id, 'pending_approval')
    if row.requested_by_user_id == auth.user.id:
        raise AppError(ErrorCode.FORBIDDEN, 'Нельзя одобрить собственную заявку')
    row.status = 'awaiting_confirmation'
    row.approved_by_user_id = auth.user.id
    row.approved_at = utcnow()
    delivered, message = issue_confirmation(db, request, row)
    _event(db, request, auth.user, 'email_sender.approve', row, f'Одобрен адрес отправителя {row.email_address}')
    db.commit()
    return DeliveryOut(delivered=delivered, message=message)


@router.post('/{sender_id}/reject', status_code=204, summary='Отклонить заявку')
def reject(sender_id: int, data: RejectIn, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = _open_row(db, sender_id, 'pending_approval')
    row.status = 'rejected'
    row.rejection_reason = data.reason
    _event(db, request, auth.user, 'email_sender.reject', row, f'Отклонён адрес отправителя {row.email_address}')
    db.commit()


@router.post('/{sender_id}/resend', response_model=DeliveryOut, summary='Повторить письмо подтверждения')
def resend(sender_id: int, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    row = _open_row(db, sender_id, 'awaiting_confirmation')
    if row.confirmation_sent_at and (utcnow() - row.confirmation_sent_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        raise AppError(ErrorCode.RATE_LIMITED, 'Письмо уже отправлено, повторить можно не раньше чем через минуту')
    delivered, message = issue_confirmation(db, request, row)
    _event(db, request, auth.user, 'email_sender.confirmation_resent', row, f'Повторно отправлено подтверждение на {row.email_address}')
    db.commit()
    return DeliveryOut(delivered=delivered, message=message)


class ConfirmOut(BaseModel):
    email_address: str


@router.post('/confirm', response_model=ConfirmOut, summary='Подтвердить адрес по ссылке из письма')
def confirm(data: ConfirmIn, request: Request, db: Session = Depends(get_db)):
    # No session: the token proves control of the mailbox. POST only, so link-prefetching scanners can't confirm.
    row = db.scalar(select(EmailSenderIdentity).where(
        EmailSenderIdentity.confirmation_token_hash == token_hash(data.token)).with_for_update())
    if (row is None or row.status != 'awaiting_confirmation' or not row.is_active
            or row.confirmation_expires_at is None or row.confirmation_expires_at <= utcnow()):
        db.rollback()
        raise AppError(ErrorCode.CONFLICT, INVALID_LINK)
    row.status = 'active'
    row.confirmed_at = utcnow()
    row.confirmation_token_hash = None
    row.confirmation_expires_at = None
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    if owner is not None:
        owner.email_sender_identity_id = row.id
    _event(db, request, owner, 'email_sender.confirm', row, f'Подтверждён адрес отправителя {row.email_address}')
    db.commit()
    return ConfirmOut(email_address=row.email_address)
```

Импорт `token_hash` из `.security`. Эндпоинт `/confirm` объявить **до** маршрутов вида `/{sender_id}` не требуется (разные методы/пути), но `/queue` и `/requests` должны быть объявлены до `DELETE /{sender_id}`, чтобы не перехватывались им. `record_event` с `actor=None` уже поддерживается (`actor.id if actor is not None else None`).

Существующий `create_sender` (общий адрес, руководитель/админ) заменить:

```python
@router.post('', response_model=SenderOut, status_code=201, summary='Добавить общий адрес отправителя')
def create_sender(data: SenderIn, request: Request, auth: AuthContext = Depends(sender_manager), db: Session = Depends(get_db)):
    existing = db.scalar(select(EmailSenderIdentity).where(EmailSenderIdentity.email_address == data.email_address))
    if existing is not None and existing.owner_user_id is None and not existing.is_active and existing.status == 'active':
        # Previously confirmed shared address: reactivation keeps its confirmation (unchanged behavior).
        existing.is_active = True
        existing.display_name = data.display_name
        _event(db, request, auth.user, 'email_sender.reactivate', existing, f'Восстановлен отправитель писем «{existing.display_name}» ({existing.email_address})')
        db.commit()
        return sender_out(existing)
    if existing is not None and existing.status != 'rejected':
        raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'email_address', 'message': 'Такой адрес уже добавлен', 'type': 'value_error'}])
    row = existing or EmailSenderIdentity(email_address=data.email_address)
    row.display_name = data.display_name
    row.owner_user_id = None
    row.is_active = True
    row.status = 'awaiting_confirmation'
    row.rejection_reason = ''
    row.created_by_user_id = auth.user.id
    row.approved_by_user_id = auth.user.id
    row.approved_at = utcnow()
    if existing is None:
        db.add(row)
    db.flush()
    issue_confirmation(db, request, row)
    _event(db, request, auth.user, 'email_sender.create', row, f'Добавлен отправитель писем «{row.display_name}» ({row.email_address})')
    db.commit()
    return sender_out(row)
```

`deactivate_sender` оставить, добавив `row.confirmation_token_hash = None`.

- [ ] **Step 5: Обновить старые тесты каталога**

В `tests/test_email_senders.py`:
- `test_supervisor_can_create_and_it_is_immediately_approved` → переименовать в `test_supervisor_creates_a_shared_sender_awaiting_confirmation`; ожидать `status == 'awaiting_confirmation'`, `is_shared is True`, `usable is False`.
- `test_any_signed_in_user_can_list_active_senders` и `test_deactivating_removes_it_from_the_selectable_list` — создавать активную строку напрямую в БД (как `_sender` из Task 6), потому что свежесозданный общий адрес теперь не виден, пока не подтверждён.
- `test_recreating_a_deactivated_sender_reactivates_the_same_row` — строку создавать в БД со `status='active'`, деактивировать через API, пересоздать через `POST` и ожидать тот же `id` и `status == 'active'`.

- [ ] **Step 6: Запустить тесты**

Run: `uv run pytest tests/test_sender_requests.py tests/test_email_senders.py tests/test_sender_guard.py -v && uv run pytest -q`
Expected: PASS; весь набор зелёный.

- [ ] **Step 7: Commit**

```bash
git add backend/app/sender_addresses.py backend/app/email_routes.py backend/tests/test_sender_requests.py backend/tests/test_email_senders.py
git commit -m "feat: request, approve and email-confirm sender addresses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Фронтенд — API и типы

**Files:**
- Rewrite: `frontend/src/api/profile.ts`
- Create: `frontend/src/api/emailSenders.ts`
- Modify: `frontend/src/api/auth.ts` (`CurrentUser`)
- Modify: `frontend/src/test/utils.tsx` (`sessionFixture`, обработчики по умолчанию `GET /profile`, `GET /email-senders`)
- Test: `frontend/src/api/profile.test.ts`

**Interfaces:**
- Produces: `Profile`, `ProfilePatch`, `Messenger`, `MessengerService`, `MESSENGER_SERVICES`, `MESSENGER_LABELS`, `profileKeys`, `useProfile()`, `useUpdateProfile()` (при успехе обновляет кэш профиля и `authKeys.me.user.full_name`); `Sender`, `QueueItem`, `Delivery`, `senderKeys`, `useSenders()`, `useRequestSender()`, `useWithdrawRequest()`, `useSenderQueue()`, `useApproveSender()`, `useRejectSender()`, `useResendConfirmation()`, `useCreateSharedSender()`, `useDeactivateSender()`, `useConfirmSender()`, `useTestSend()`.

- [ ] **Step 1: Написать падающий тест**

`frontend/src/api/profile.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { MESSENGER_LABELS, MESSENGER_SERVICES } from "./profile";

describe("profile api constants", () => {
  it("lists the six messenger services with labels", () => {
    expect(MESSENGER_SERVICES).toEqual(["telegram", "whatsapp", "viber", "vk", "max", "other"]);
    for (const service of MESSENGER_SERVICES) expect(MESSENGER_LABELS[service]).toBeTruthy();
  });
});
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `cd frontend && npx vitest run src/api/profile.test.ts`
Expected: FAIL — `MESSENGER_SERVICES` не экспортируется.

- [ ] **Step 3: `profile.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { authKeys, type Session } from "./auth";

/* Types of backend/app/profile_routes.py */

export const MESSENGER_SERVICES = ["telegram", "whatsapp", "viber", "vk", "max", "other"] as const;
export type MessengerService = (typeof MESSENGER_SERVICES)[number];
export const MESSENGER_LABELS: Record<MessengerService, string> = {
  telegram: "Telegram", whatsapp: "WhatsApp", viber: "Viber", vk: "ВКонтакте", max: "MAX", other: "Другое",
};

export interface Messenger { service: MessengerService; handle: string; }

export interface Profile {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  timezone: string;
  messengers: Messenger[];
  email_sender_identity_id: number | null;
}

export type ProfilePatch = Partial<Pick<Profile, "first_name" | "last_name" | "phone" | "timezone" | "messengers">> & {
  /** 0 clears the selection. */
  email_sender_identity_id?: number;
};

export const profileKeys = { me: ["profile"] as const };

export const useProfile = () =>
  useQuery({ queryKey: profileKeys.me, queryFn: () => apiRequest<Profile>("/profile") });

export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (data: ProfilePatch) => apiRequest<Profile>("/profile", "PATCH", data),
    onSuccess: (profile) => {
      client.setQueryData(profileKeys.me, profile);
      client.setQueryData<Session>(authKeys.me, (session) =>
        session && {
          ...session,
          user: {
            ...session.user,
            full_name: profile.full_name, first_name: profile.first_name, last_name: profile.last_name,
            phone: profile.phone, timezone: profile.timezone, messengers: profile.messengers,
          },
        },
      );
    },
  });
}
```

- [ ] **Step 4: `emailSenders.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./client";
import { profileKeys } from "./profile";

/* Types of backend/app/email_routes.py */

export type SenderStatus = "pending_approval" | "awaiting_confirmation" | "active" | "rejected";

export interface Sender {
  id: number;
  email_address: string;
  display_name: string;
  is_active: boolean;
  status: SenderStatus;
  is_shared: boolean;
  rejection_reason: string;
  usable: boolean;
}

export interface QueueItem extends Sender { requested_by: string; requested_at: string | null; }
export interface Delivery { delivered: boolean; message: string; }
export interface SenderRequest { email_address: string; display_name: string; }

export const SENDER_STATUS_LABELS: Record<SenderStatus, string> = {
  pending_approval: "Ждёт одобрения",
  awaiting_confirmation: "Ждёт подтверждения по email",
  active: "Подтверждён",
  rejected: "Отклонён",
};

export const senderKeys = { mine: ["email-senders"] as const, queue: ["email-senders", "queue"] as const };

export const useSenders = () =>
  useQuery({ queryKey: senderKeys.mine, queryFn: () => apiRequest<Sender[]>("/email-senders") });

export const useSenderQueue = () =>
  useQuery({ queryKey: senderKeys.queue, queryFn: () => apiRequest<QueueItem[]>("/email-senders/queue") });

function useSenderMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: senderKeys.mine });
      void client.invalidateQueries({ queryKey: profileKeys.me });
    },
  });
}

export const useRequestSender = () =>
  useSenderMutation((data: SenderRequest) => apiRequest<Sender>("/email-senders/requests", "POST", data));
export const useWithdrawRequest = () =>
  useSenderMutation((id: number) => apiRequest<void>(`/email-senders/requests/${id}`, "DELETE"));
export const useApproveSender = () =>
  useSenderMutation((id: number) => apiRequest<Delivery>(`/email-senders/${id}/approve`, "POST"));
export const useRejectSender = () =>
  useSenderMutation(({ id, reason }: { id: number; reason: string }) =>
    apiRequest<void>(`/email-senders/${id}/reject`, "POST", { reason }));
export const useResendConfirmation = () =>
  useSenderMutation((id: number) => apiRequest<Delivery>(`/email-senders/${id}/resend`, "POST"));
export const useCreateSharedSender = () =>
  useSenderMutation((data: SenderRequest) => apiRequest<Sender>("/email-senders", "POST", data));
export const useDeactivateSender = () =>
  useSenderMutation((id: number) => apiRequest<void>(`/email-senders/${id}`, "DELETE"));
export const useTestSend = () =>
  useMutation({ mutationFn: () => apiRequest<Delivery>("/email-senders/test", "POST") });
export const useConfirmSender = () =>
  useMutation({
    mutationFn: (token: string) => apiRequest<{ email_address: string }>("/email-senders/confirm", "POST", { token }),
  });
```

`useSenderMutation` вызывает `invalidateQueries` для очереди тоже: добавить `void client.invalidateQueries({ queryKey: senderKeys.queue });` — ключ очереди начинается с `["email-senders"]`, поэтому инвалидация `senderKeys.mine` уже затрагивает её (префиксное совпадение TanStack Query). Отдельный вызов не нужен.

- [ ] **Step 5: `auth.ts` и тестовые фикстуры**

`CurrentUser` в `auth.ts`:

```typescript
export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  roles: string[];
  phone: string;
  timezone: string;
  messengers: { service: string; handle: string }[];
}
```

`test/utils.tsx` — `sessionFixture`:

```typescript
export const sessionFixture = (
  roles: string[] = ["crm-supervisor"],
  csrfToken = CSRF_TOKEN,
  user: Partial<Session["user"]> = {},
): Session => ({
  user: {
    id: 1,
    email: "anna.petrova@example.test",
    full_name: "Анна Петрова",
    first_name: "Анна",
    last_name: "Петрова",
    roles,
    phone: "",
    timezone: "Europe/Moscow",
    messengers: [],
    ...user,
  },
  csrf_token: csrfToken,
});
```

и в `handlers` по умолчанию `mockApi` добавить:

```typescript
    "GET /profile": () => ({
      id: 1, email: "anna.petrova@example.test", first_name: "Анна", last_name: "Петрова",
      full_name: "Анна Петрова", phone: "", timezone: "Europe/Moscow", messengers: [],
      email_sender_identity_id: null,
    }),
    "GET /email-senders": () => [],
    "GET /email-senders/queue": () => [],
```

Найти все вызовы `sessionFixture(..., { phone_verified_at: ... })` (`grep -rn "phone_verified_at" frontend/src`) и убрать этот ключ.

- [ ] **Step 6: Проверка типов и тесты**

Run: `npx tsc --noEmit && npx vitest run src/api`
Expected: PASS. Ошибки типов в `SettingsProfilePage.tsx` (использует удалённые хуки) допустимы до Task 9 — если `tsc` падает только там, переходить к коммиту; остальные ошибки исправить.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/profile.ts frontend/src/api/emailSenders.ts frontend/src/api/auth.ts frontend/src/test/utils.tsx frontend/src/api/profile.test.ts
git commit -m "feat(frontend): profile and sender address API hooks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Фронтенд — страница «Личный профиль»

**Files:**
- Rewrite: `frontend/src/pages/settings/SettingsProfilePage.tsx`
- Create: `frontend/src/pages/settings/SenderAddressPanel.tsx`
- Rewrite: `frontend/src/pages/settings/settingsProfile.test.tsx`

**Interfaces:**
- Consumes: хуки Task 8.
- Produces: `SenderAddressPanel` (без пропсов).

- [ ] **Step 1: Написать падающие тесты**

`frontend/src/pages/settings/settingsProfile.test.tsx`:

```typescript
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp } from "../../test/utils";

const profile = {
  id: 1, email: "anna.petrova@example.test", first_name: "Анна", last_name: "Петрова",
  full_name: "Анна Петрова", phone: "", timezone: "Europe/Moscow", messengers: [],
  email_sender_identity_id: null as number | null,
};

describe("settings profile", () => {
  it("saves personal data and messengers in one request", async () => {
    const api = mockApi({ "PATCH /profile": (body) => ({ ...profile, ...(body as object), full_name: "Анна Смирнова" }) });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Фамилия"), { target: { value: "Смирнова" } });
    fireEvent.change(screen.getByLabelText("Телефон"), { target: { value: "+79991234567" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить мессенджер" }));
    fireEvent.change(screen.getByLabelText("Аккаунт 1"), { target: { value: "@anna" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText("Изменения сохранены");
    expect(api.calls.find((c) => c.method === "PATCH" && c.path === "/profile")?.body).toEqual({
      first_name: "Анна", last_name: "Смирнова", phone: "+79991234567", timezone: "Europe/Moscow",
      messengers: [{ service: "telegram", handle: "@anna" }],
    });
  });

  it("keeps the form filled and shows the server error when Keycloak is down", async () => {
    mockApi({ "PATCH /profile": () => { throw apiError(503, "SERVICE_UNAVAILABLE", "Не удалось сохранить имя: сервис учётных записей недоступен, попробуйте позже"); } });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Фамилия"), { target: { value: "Смирнова" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByText(/сервис учётных записей недоступен/);
    expect((screen.getByLabelText("Фамилия") as HTMLInputElement).value).toBe("Смирнова");
  });

  it("shows no phone-verification banner or SMS step", async () => {
    mockApi();
    renderApp("/settings/profile");
    await screen.findByLabelText("Имя");
    expect(screen.queryByText(/не до конца прошли регистрацию/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Отправить код" })).toBeNull();
  });

  it("marks a stored sender selection that is no longer usable", async () => {
    mockApi({
      "GET /profile": () => ({ ...profile, email_sender_identity_id: 7 }),
      "GET /email-senders": () => [{ id: 7, email_address: "old@uni.test", display_name: "Старый", is_active: false,
        status: "active", is_shared: true, rejection_reason: "", usable: false }],
    });
    renderApp("/settings/profile");
    await screen.findByText(/old@uni.test — недоступен/);
  });

  it("submits a personal sender request and shows its status", async () => {
    const api = mockApi({
      "POST /email-senders/requests": () => ({ id: 3, email_address: "anna@uni.test", display_name: "Анна",
        is_active: true, status: "pending_approval", is_shared: false, rejection_reason: "", usable: false }),
    });
    renderApp("/settings/profile");
    fireEvent.change(await screen.findByLabelText("Новый адрес"), { target: { value: "anna@uni.test" } });
    fireEvent.change(screen.getByLabelText("Имя отправителя"), { target: { value: "Анна" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить на одобрение" }));
    await waitFor(() => expect(api.callsTo("POST", "/email-senders/requests")).toHaveLength(1));
  });
});
```

Проверить в `test/utils.tsx`, как обработчик `mockApi` получает тело запроса (сигнатура `Handler`) и как выбрасывается ошибка (`apiError(...)` возвращает объект для `throw` или для `return`) — привести тесты к фактической сигнатуре, как в других тестах страниц.

- [ ] **Step 2: Запустить — должен упасть**

Run: `npx vitest run src/pages/settings/settingsProfile.test.tsx`
Expected: FAIL — нет поля «Фамилия».

- [ ] **Step 3: `SettingsProfilePage.tsx`**

```tsx
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { ApiError, errorText } from "../../api/client";
import {
  MESSENGER_LABELS, MESSENGER_SERVICES, useProfile, useUpdateProfile,
  type Messenger, type MessengerService,
} from "../../api/profile";
import { SenderAddressPanel } from "./SenderAddressPanel";

const TIME_ZONES: string[] =
  typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : ["Europe/Moscow"];

export function SettingsProfilePage() {
  const profile = useProfile();
  const update = useUpdateProfile();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [timezone, setTimezone] = useState("Europe/Moscow");
  const [messengers, setMessengers] = useState<Messenger[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!profile.data) return;
    setFirstName(profile.data.first_name);
    setLastName(profile.data.last_name);
    setPhone(profile.data.phone);
    setTimezone(profile.data.timezone);
    setMessengers(profile.data.messengers);
  }, [profile.data]);

  const zones = useMemo(() => (TIME_ZONES.includes(timezone) ? TIME_ZONES : [timezone, ...TIME_ZONES]), [timezone]);
  const error = update.error;
  const fieldError = (field: string) => (error instanceof ApiError ? error.fieldMessage(field) : undefined);

  function setMessenger(index: number, patch: Partial<Messenger>) {
    setMessengers((list) => list.map((m, i) => (i === index ? { ...m, ...patch } : m)));
    setSaved(false);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    update.mutate(
      {
        first_name: firstName, last_name: lastName, phone, timezone,
        messengers: messengers.filter((m) => m.handle.trim() !== ""),
      },
      { onSuccess: () => setSaved(true) },
    );
  }

  if (profile.isPending) return <section className="panel"><p className="muted">Загрузка…</p></section>;
  if (profile.isError) return <section className="panel"><p className="danger" role="alert">{errorText(profile.error)}</p></section>;

  return (
    <>
      <form className="panel wizard-body" onSubmit={submit} aria-labelledby="profile-personal-title">
        <div className="section-head">
          <div>
            <h2 id="profile-personal-title">Личные данные</h2>
            <p>Имя и фамилия сохраняются в учётной записи для входа.</p>
          </div>
        </div>
        <div className="form-row">
          <label>
            Имя
            <input value={firstName} maxLength={100} required onChange={(e) => { setFirstName(e.target.value); setSaved(false); }}
              aria-invalid={fieldError("first_name") ? true : undefined} />
            {fieldError("first_name") && <small className="field-error danger">{fieldError("first_name")}</small>}
          </label>
          <label>
            Фамилия
            <input value={lastName} maxLength={100} required onChange={(e) => { setLastName(e.target.value); setSaved(false); }}
              aria-invalid={fieldError("last_name") ? true : undefined} />
          </label>
        </div>
        <label>
          Email
          <input value={profile.data.email} readOnly aria-readonly="true" />
          <small className="field-hint">Меняется администратором в учётной записи.</small>
        </label>
        <div className="form-row">
          <label>
            Телефон
            <input type="tel" value={phone} placeholder="+7XXXXXXXXXX" onChange={(e) => { setPhone(e.target.value); setSaved(false); }}
              aria-invalid={fieldError("phone") ? true : undefined} />
            {fieldError("phone") && <small className="field-error danger">{fieldError("phone")}</small>}
          </label>
          <label>
            Часовой пояс
            <select value={timezone} onChange={(e) => { setTimezone(e.target.value); setSaved(false); }}>
              {zones.map((zone) => <option key={zone} value={zone}>{zone.replace(/_/g, " ")}</option>)}
            </select>
          </label>
        </div>

        <fieldset className="messenger-list">
          <legend>Мессенджеры</legend>
          {messengers.map((messenger, index) => (
            <div className="form-row" key={index}>
              <label>
                Сервис {index + 1}
                <select value={messenger.service} onChange={(e) => setMessenger(index, { service: e.target.value as MessengerService })}>
                  {MESSENGER_SERVICES.map((s) => <option key={s} value={s}>{MESSENGER_LABELS[s]}</option>)}
                </select>
              </label>
              <label>
                Аккаунт {index + 1}
                <input value={messenger.handle} maxLength={101} placeholder="@username или номер"
                  onChange={(e) => setMessenger(index, { handle: e.target.value })} />
              </label>
              <button type="button" className="secondary icon-button" aria-label={`Удалить мессенджер ${index + 1}`}
                onClick={() => { setMessengers((list) => list.filter((_, i) => i !== index)); setSaved(false); }}>
                <Trash2 size={16} aria-hidden="true" />
              </button>
            </div>
          ))}
          {messengers.length < 10 && (
            <button type="button" className="secondary"
              onClick={() => { setMessengers((list) => [...list, { service: "telegram", handle: "" }]); setSaved(false); }}>
              <Plus size={16} aria-hidden="true" /> Добавить мессенджер
            </button>
          )}
        </fieldset>

        {error && !fieldError("first_name") && !fieldError("phone") && (
          <p className="danger" role="alert">{errorText(error)}</p>
        )}
        {saved && <p className="text-green" role="status">Изменения сохранены</p>}
        <div className="wizard-actions">
          <button className="primary" disabled={update.isPending}>{update.isPending ? "Сохраняем…" : "Сохранить"}</button>
        </div>
      </form>
      <SenderAddressPanel />
    </>
  );
}
```

Если в `styles.css` нет классов `messenger-list`/`icon-button` — использовать существующие (`form-row`, `secondary`) и добавить минимальные правила рядом со стилями `.wizard-body`; сверить с токенами дизайна ветки `ai/design-tokens` не требуется — работа идёт от ветки GPT.

- [ ] **Step 4: `SenderAddressPanel.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import {
  SENDER_STATUS_LABELS, useRequestSender, useSenders, useTestSend, useWithdrawRequest,
} from "../../api/emailSenders";
import { useProfile, useUpdateProfile } from "../../api/profile";

export function SenderAddressPanel() {
  const profile = useProfile();
  const senders = useSenders();
  const update = useUpdateProfile();
  const requestSender = useRequestSender();
  const withdraw = useWithdrawRequest();
  const testSend = useTestSend();
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");

  const list = senders.data ?? [];
  const selectedId = profile.data?.email_sender_identity_id ?? null;
  const selected = list.find((s) => s.id === selectedId);
  const usable = list.filter((s) => s.usable);
  const own = list.filter((s) => !s.is_shared && !s.usable);
  const hasOpen = own.some((s) => s.status === "pending_approval" || s.status === "awaiting_confirmation");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    requestSender.mutate({ email_address: address.trim(), display_name: displayName.trim() }, {
      onSuccess: () => { setAddress(""); setDisplayName(""); },
    });
  }

  return (
    <section className="panel" aria-labelledby="profile-sender-title">
      <div className="section-head">
        <div>
          <h2 id="profile-sender-title">Адрес отправителя</h2>
          <p>С этого адреса уходят письма вузам. Новый адрес одобряет руководитель, затем его нужно подтвердить по ссылке из письма.</p>
        </div>
      </div>
      <div className="wizard-body">
        {selectedId !== null && selected && !selected.usable && (
          <p className="danger" role="status">{selected.email_address} — недоступен. Выберите другой адрес.</p>
        )}
        <label>
          Отправлять от имени
          <select value={selected?.usable ? String(selectedId) : ""} disabled={update.isPending}
            onChange={(e) => update.mutate({ email_sender_identity_id: Number(e.target.value) || 0 })}>
            <option value="">Системный адрес UniCRM</option>
            {usable.map((s) => (
              <option key={s.id} value={s.id}>{s.display_name} &lt;{s.email_address}&gt;{s.is_shared ? " · общий" : ""}</option>
            ))}
          </select>
        </label>
        {update.isError && <p className="danger" role="alert">{errorText(update.error)}</p>}

        {own.map((s) => (
          <div key={s.id} className="sender-request">
            <span><strong>{s.email_address}</strong> — {SENDER_STATUS_LABELS[s.status]}</span>
            {s.status === "rejected" && s.rejection_reason && <small className="muted"> · Причина: {s.rejection_reason}</small>}
            {(s.status === "pending_approval" || s.status === "awaiting_confirmation") && (
              <button type="button" className="secondary" disabled={withdraw.isPending} onClick={() => withdraw.mutate(s.id)}>
                Отозвать заявку
              </button>
            )}
          </div>
        ))}

        {!hasOpen && (
          <form onSubmit={submit} className="form-row">
            <label>
              Новый адрес
              <input type="email" required maxLength={254} value={address} onChange={(e) => setAddress(e.target.value)}
                aria-invalid={requestSender.isError ? true : undefined} />
            </label>
            <label>
              Имя отправителя
              <input required maxLength={200} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
            <button className="primary" disabled={requestSender.isPending}>
              {requestSender.isPending ? "Отправляем…" : "Отправить на одобрение"}
            </button>
          </form>
        )}
        {requestSender.isError && <p className="danger" role="alert">{errorText(requestSender.error)}</p>}

        <div className="wizard-actions">
          <button type="button" className="secondary" disabled={testSend.isPending} onClick={() => testSend.mutate()}>
            {testSend.isPending ? "Отправляем…" : "Отправить тестовое письмо себе"}
          </button>
        </div>
        {testSend.data && <p role="status" className={testSend.data.delivered ? "text-green" : "muted"}>{testSend.data.message}</p>}
        {testSend.isError && <p className="danger" role="alert">{errorText(testSend.error)}</p>}
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Тесты и типы**

Run: `npx tsc --noEmit && npx vitest run src/pages/settings`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/settings/SettingsProfilePage.tsx frontend/src/pages/settings/SenderAddressPanel.tsx frontend/src/pages/settings/settingsProfile.test.tsx frontend/src/styles.css
git commit -m "feat(frontend): editable profile with messengers and sender address requests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Фронтенд — очередь и общие адреса в «Организации»

**Files:**
- Rewrite: `frontend/src/pages/settings/SettingsOrganizationPage.tsx`
- Create: `frontend/src/pages/settings/SenderQueuePanel.tsx`
- Test: `frontend/src/pages/settings/settingsOrganization.test.tsx`

**Interfaces:**
- Consumes: `useSenderQueue`, `useApproveSender`, `useRejectSender`, `useResendConfirmation`, `useCreateSharedSender`, `useDeactivateSender`, `useSenders` (Task 8); `useSession` из `app/AuthGate`; `ROLES` из `lib/user`.

- [ ] **Step 1: Написать падающие тесты**

`frontend/src/pages/settings/settingsOrganization.test.tsx`:

```typescript
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, renderApp, sessionFixture } from "../../test/utils";

const pending = {
  id: 5, email_address: "anna@uni.test", display_name: "Анна", is_active: true, status: "pending_approval",
  is_shared: false, rejection_reason: "", usable: false, requested_by: "Анна Петрова", requested_at: "2026-09-27T10:00:00Z",
};

describe("organization sender queue", () => {
  it("lets a supervisor approve and shows the delivery message", async () => {
    const api = mockApi({
      "GET /email-senders/queue": () => [pending],
      "POST /email-senders/5/approve": () => ({ delivered: false, message: "Почтовый провайдер не настроен: письмо подтверждения записано только в журнал сервера." }),
    });
    renderApp("/settings/organization");
    fireEvent.click(await screen.findByRole("button", { name: "Одобрить anna@uni.test" }));
    await screen.findByText(/записано только в журнал сервера/);
    expect(api.callsTo("POST", "/email-senders/5/approve")).toHaveLength(1);
  });

  it("rejects with a reason", async () => {
    const api = mockApi({ "GET /email-senders/queue": () => [pending], "POST /email-senders/5/reject": () => undefined });
    renderApp("/settings/organization");
    fireEvent.click(await screen.findByRole("button", { name: "Отклонить anna@uni.test" }));
    fireEvent.change(screen.getByLabelText("Причина отказа"), { target: { value: "Чужой домен" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить отказ" }));
    await waitFor(() => expect(api.calls.find((c) => c.path === "/email-senders/5/reject")?.body).toEqual({ reason: "Чужой домен" }));
  });

  it("shows only the placeholder text to a regular user", async () => {
    mockApi({ "GET /auth/me": () => sessionFixture(["crm-user"]) });
    renderApp("/settings/organization");
    await screen.findByText("Реквизиты и контактные данные организации.");
    expect(screen.queryByText("Заявки на адреса отправителей")).toBeNull();
  });
});
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `npx vitest run src/pages/settings/settingsOrganization.test.tsx`
Expected: FAIL — нет кнопки «Одобрить anna@uni.test».

- [ ] **Step 3: `SenderQueuePanel.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { errorText } from "../../api/client";
import {
  SENDER_STATUS_LABELS, useApproveSender, useCreateSharedSender, useDeactivateSender, useRejectSender,
  useResendConfirmation, useSenderQueue, useSenders,
} from "../../api/emailSenders";
import { formatDateTime } from "../../lib/format";

export function SenderQueuePanel() {
  const queue = useSenderQueue();
  const senders = useSenders();
  const approve = useApproveSender();
  const reject = useRejectSender();
  const resend = useResendConfirmation();
  const create = useCreateSharedSender();
  const deactivate = useDeactivateSender();
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [address, setAddress] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [notice, setNotice] = useState("");

  const actionError = approve.error ?? reject.error ?? resend.error ?? create.error ?? deactivate.error;
  const shared = (senders.data ?? []).filter((s) => s.is_shared);

  function confirmReject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rejecting === null) return;
    reject.mutate({ id: rejecting, reason: reason.trim() }, { onSuccess: () => { setRejecting(null); setReason(""); } });
  }

  function addShared(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate({ email_address: address.trim(), display_name: displayName.trim() }, {
      onSuccess: (s) => { setAddress(""); setDisplayName(""); setNotice(`На ${s.email_address} отправлено письмо подтверждения.`); },
    });
  }

  return (
    <>
      <section className="panel" aria-labelledby="sender-queue-title">
        <h2 id="sender-queue-title">Заявки на адреса отправителей</h2>
        {queue.isPending && <p className="muted">Загрузка…</p>}
        {queue.data?.length === 0 && <p className="muted">Новых заявок нет.</p>}
        <ul className="plain-list">
          {queue.data?.map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.email_address}</strong> · {item.display_name} · {item.is_shared ? "общий" : item.requested_by}
                {item.requested_at && <span className="muted"> · {formatDateTime(item.requested_at)}</span>}
                <span className="muted"> · {SENDER_STATUS_LABELS[item.status]}</span>
              </div>
              {item.status === "pending_approval" && (
                <div className="wizard-actions">
                  <button type="button" className="primary" aria-label={`Одобрить ${item.email_address}`} disabled={approve.isPending}
                    onClick={() => approve.mutate(item.id, { onSuccess: (d) => setNotice(d.message) })}>Одобрить</button>
                  <button type="button" className="secondary" aria-label={`Отклонить ${item.email_address}`}
                    onClick={() => { setRejecting(item.id); setReason(""); }}>Отклонить</button>
                </div>
              )}
              {item.status === "awaiting_confirmation" && (
                <button type="button" className="secondary" disabled={resend.isPending}
                  onClick={() => resend.mutate(item.id, { onSuccess: (d) => setNotice(d.message) })}>Отправить письмо ещё раз</button>
              )}
              {rejecting === item.id && (
                <form onSubmit={confirmReject} className="form-row">
                  <label>
                    Причина отказа
                    <input maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
                  </label>
                  <button className="primary" disabled={reject.isPending}>Подтвердить отказ</button>
                  <button type="button" className="secondary" onClick={() => setRejecting(null)}>Отмена</button>
                </form>
              )}
            </li>
          ))}
        </ul>
        {notice && <p role="status" className="muted">{notice}</p>}
        {actionError && <p className="danger" role="alert">{errorText(actionError)}</p>}
      </section>

      <section className="panel" aria-labelledby="shared-senders-title">
        <h2 id="shared-senders-title">Общие адреса</h2>
        <ul className="plain-list">
          {shared.map((s) => (
            <li key={s.id}>
              <strong>{s.email_address}</strong> · {s.display_name}
              <button type="button" className="secondary" aria-label={`Деактивировать ${s.email_address}`}
                disabled={deactivate.isPending} onClick={() => deactivate.mutate(s.id)}>Деактивировать</button>
            </li>
          ))}
        </ul>
        <form onSubmit={addShared} className="form-row">
          <label>
            Адрес
            <input type="email" required maxLength={254} value={address} onChange={(e) => setAddress(e.target.value)} />
          </label>
          <label>
            Имя отправителя
            <input required maxLength={200} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <button className="primary" disabled={create.isPending}>Добавить общий адрес</button>
        </form>
      </section>
    </>
  );
}
```

`GET /email-senders` возвращает общие адреса только активные и подтверждённые; общие адреса, ждущие подтверждения, видны в очереди со статусом «Ждёт подтверждения по email».

- [ ] **Step 4: `SettingsOrganizationPage.tsx`**

```tsx
import { useSession } from "../../app/AuthGate";
import { ROLES } from "../../lib/user";
import { SenderQueuePanel } from "./SenderQueuePanel";
import { SettingsPlaceholderPage } from "./SettingsPlaceholderPage";

export function SettingsOrganizationPage() {
  const { user } = useSession();
  const manager = user.roles.includes(ROLES.supervisor) || user.roles.includes(ROLES.admin);
  return (
    <>
      <SettingsPlaceholderPage heading="Организация" subtitle="Реквизиты и контактные данные организации." />
      {manager && <SenderQueuePanel />}
    </>
  );
}
```

Свериться с `lib/user.ts`, как называются ключи ролей (`ROLES.supervisor`, `ROLES.admin`), и поправить при расхождении.

- [ ] **Step 5: Тесты**

Run: `npx tsc --noEmit && npx vitest run src/pages/settings`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/settings/SettingsOrganizationPage.tsx frontend/src/pages/settings/SenderQueuePanel.tsx frontend/src/pages/settings/settingsOrganization.test.tsx
git commit -m "feat(frontend): sender address queue and shared addresses for supervisors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Фронтенд — публичная страница подтверждения

**Files:**
- Create: `frontend/src/pages/ConfirmSenderPage.tsx`
- Modify: `frontend/src/app/App.tsx` (`AppRoutes`), `frontend/src/app/navigation.ts` (`paths.confirmSender`)
- Test: `frontend/src/pages/confirmSender.test.tsx`

**Interfaces:**
- Consumes: `useConfirmSender` (Task 8).
- Produces: `paths.confirmSender = "/confirm-sender"`.

- [ ] **Step 1: Написать падающие тесты**

`frontend/src/pages/confirmSender.test.tsx`:

```typescript
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp } from "../test/utils";

describe("confirm sender page", () => {
  it("does nothing until the button is pressed, then confirms", async () => {
    const api = mockApi({
      "GET /auth/me": () => { throw apiError(401, "UNAUTHENTICATED", "Нужно войти"); },
      "POST /email-senders/confirm": () => ({ email_address: "anna@uni.test" }),
    });
    renderApp("/confirm-sender?token=abc");
    await screen.findByRole("button", { name: "Подтвердить" });
    expect(api.callsTo("POST", "/email-senders/confirm")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await screen.findByText(/anna@uni.test подтверждён/);
    expect(api.calls.find((c) => c.path === "/email-senders/confirm")?.body).toEqual({ token: "abc" });
  });

  it("shows the server message for an invalid link", async () => {
    mockApi({ "POST /email-senders/confirm": () => { throw apiError(409, "CONFLICT", "Ссылка недействительна или устарела"); } });
    renderApp("/confirm-sender?token=bad");
    fireEvent.click(await screen.findByRole("button", { name: "Подтвердить" }));
    await screen.findByText("Ссылка недействительна или устарела");
  });

  it("explains a missing token", async () => {
    mockApi();
    renderApp("/confirm-sender");
    await screen.findByText(/В ссылке нет кода подтверждения/);
  });
});
```

- [ ] **Step 2: Запустить — должен упасть**

Run: `npx vitest run src/pages/confirmSender.test.tsx`
Expected: FAIL — `AuthGate` показывает вход вместо кнопки.

- [ ] **Step 3: Страница**

`frontend/src/pages/ConfirmSenderPage.tsx`:

```tsx
import { useSearchParams } from "react-router";
import { errorText } from "../api/client";
import { useConfirmSender } from "../api/emailSenders";

/** Public (outside AuthGate): the mailed link proves mailbox control. Confirmation needs a click,
 * so link-prefetching mail scanners never confirm an address by opening it. */
export function ConfirmSenderPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const confirm = useConfirmSender();

  return (
    <main className="auth-screen">
      <section className="panel">
        <h1>Подтверждение адреса отправителя</h1>
        {!token && <p className="danger">В ссылке нет кода подтверждения. Откройте ссылку из письма целиком.</p>}
        {token && !confirm.isSuccess && (
          <>
            <p>Нажмите кнопку, чтобы подтвердить, что этот ящик можно использовать как адрес отправителя UniCRM.</p>
            <button type="button" className="primary" disabled={confirm.isPending} onClick={() => confirm.mutate(token)}>
              {confirm.isPending ? "Подтверждаем…" : "Подтвердить"}
            </button>
          </>
        )}
        {confirm.isSuccess && <p className="text-green" role="status">Адрес {confirm.data.email_address} подтверждён. Окно можно закрыть.</p>}
        {confirm.isError && <p className="danger" role="alert">{errorText(confirm.error)}</p>}
      </section>
    </main>
  );
}
```

Класс `auth-screen` взять из разметки экрана входа в `AuthGate.tsx` (посмотреть, какой класс он использует для страницы без бокового меню) и заменить им.

- [ ] **Step 4: Маршрут вне `AuthGate`**

`navigation.ts` — в `paths` добавить `confirmSender: "/confirm-sender",`.

`App.tsx`:

```tsx
import { useLocation } from "react-router";
import { ConfirmSenderPage } from "../pages/ConfirmSenderPage";

export function AppRoutes() {
  const location = useLocation();
  if (location.pathname === paths.confirmSender) return <ConfirmSenderPage />;
  return (
    <AuthGate>
      {/* existing <Routes> unchanged */}
    </AuthGate>
  );
}
```

(`useLocation` добавить в существующий импорт из `react-router`; тело `<AuthGate>` оставить без изменений.)

Проверить `frontend/nginx.conf` и `nginx.public.conf`: SPA-запасной маршрут (`try_files $uri /index.html`) должен покрывать `/confirm-sender`. Если там перечислены разрешённые пути — добавить.

- [ ] **Step 5: Тесты**

Run: `npx tsc --noEmit && npx vitest run`
Expected: PASS весь фронтенд-набор.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ConfirmSenderPage.tsx frontend/src/pages/confirmSender.test.tsx frontend/src/app/App.tsx frontend/src/app/navigation.ts
git commit -m "feat(frontend): public click-to-confirm page for sender addresses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Документация и итоговая проверка

**Files:**
- Modify: `docs/api/admin.md` или создать `docs/api/profile.md` и `docs/api/email-senders.md` (посмотреть, где описан `/email-senders` сейчас: `grep -rln "email-senders" docs/api`)
- Modify: `docs/decisions.md` (новые записи со следующими свободными номерами D-…)

- [ ] **Step 1: API-документация**

Описать: `GET/PATCH /api/v1/profile` (поля, ошибки 422/503, правило имени), удаление `/profile/phone*`, все эндпоинты Task 7 с ролями и кодами ошибок, `/auth/me` без `phone_verified_at`.

- [ ] **Step 2: Решения**

В `docs/decisions.md` добавить (номера — следующие свободные):
- Отмена SMS-подтверждения телефона профиля (заменяет D-155–D-157): телефон — обычное поле; таблица кодов остаётся без использования.
- Имя пользователя хранится в Keycloak, CRM — зеркало; переименование переписывает `launches.owner` у связанных строк (`owner_user_id`), несвязанные не меняются; дубликат имени через профиль запрещён.
- Адреса отправителей: личные — заявка → одобрение `crm-supervisor`/`crm-admin` (не себе) → подтверждение по ссылке 48 ч; общие — добавление руководителем → подтверждение; перед каждой отправкой свежая проверка владельца и статуса.

- [ ] **Step 3: Полная проверка**

```bash
cd backend && uv run pytest -q
cd ../frontend && npx tsc --noEmit && npx eslint . && npx vitest run && npm run build
```

Expected: всё зелёное; записать итоговые числа тестов.

- [ ] **Step 4: Проверка миграции на копии рабочей БД**

Только чтение рабочей БД, изменения — в копии:

```bash
docker compose exec -T db pg_dump -U crm -Fc edu_crm > /private/tmp/edu_crm_before_0025.dump
docker compose exec -T db psql -U crm -c "CREATE DATABASE edu_crm_0025_check"
docker compose exec -T db pg_restore -U crm -d edu_crm_0025_check < /private/tmp/edu_crm_before_0025.dump
cd backend && DATABASE_URL=postgresql+psycopg://crm:<пароль из deploy/local>@127.0.0.1:5432/edu_crm_0025_check uv run alembic upgrade head
```

Имя БД и пользователя свериться с `compose.yaml`/`deploy/local/*.env`. До и после `upgrade` сравнить:

```sql
SELECT count(*) FROM email_sender_identities;
SELECT id, email_sender_identity_id FROM users ORDER BY id;
SELECT count(*) FILTER (WHERE owner_user_id IS NOT NULL) AS linked, count(*) AS total FROM launches;
```

Число адресов и выбор пользователей должны совпасть; отчёт «связано N из M взаимодействий» передать владельцу. Затем `DROP DATABASE edu_crm_0025_check` и удалить дамп.

- [ ] **Step 5: Commit**

```bash
git add docs/api docs/decisions.md
git commit -m "docs: profile, rename rule and sender address approval

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Передать владельцу**

Сообщить: ветка `ai/profile-senders`, числа тестов, отчёт миграции на копии. Выпуск в рабочую систему — только по отдельному решению владельца (резервная копия → миграция → проверка входа).
