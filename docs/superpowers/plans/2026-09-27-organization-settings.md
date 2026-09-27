# Настройки → Организация — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Карточка организации (данные владельца), правка администратором, просмотр всеми, название в меню, на экране входа, в выгрузках и письмах.

**Architecture:** Таблица `organization_profile` (одна строка, миграция `0026` с данными владельца); `app/organization.py` — модель ответа, проверка полей, `organization_name(db)`; `app/organization_routes.py` — `GET/PUT /organization`, публичный `GET /organization/brand`; отчёты, графики и письма берут название через `organization_name(db)`. Фронтенд: `api/organization.ts`, страница «Организация», бренд в `Layout.tsx` и `AuthGate.tsx`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest; React, TanStack Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-27-organization-settings-design.md`

## Global Constraints

- Ветка `ai/profile-senders` (продолжение среза 1), миграция `revision='0026'`, `down_revision='0025'`.
- Правка — только `crm-admin`/`crm-superadmin`; чтение — `ALL_ROLES`; `brand` — без сессии, только `name`.
- Сообщения об ошибках — на русском, через `AppError(VALIDATION_ERROR, details=[...])`.
- Тесты — на изолированной БД `TEST_DATABASE_URL=postgresql+psycopg://crm:test-only@127.0.0.1:55432/postgres`, запуск `.venv/bin/python -m pytest`.
- Не пушить, не выпускать; коммиты с `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Правка при недоступной сессии администратора с устаревшим CSRF — стандартная обработка клиента; ничего нового.
- Название организации с кавычками/угловыми скобками — в PDF экранируется (`esc`), в письме — простой текст.
- Одновременные правки двумя администраторами — побеждает последняя, журнал фиксирует обе (явная блокировка не требуется).
- Ошибка `/organization/brand` на экране входа — вход работает, строка названия просто не показывается.
- Телефон, введённый как `8 495 196-62-05`, сохраняется нормализованным и показывается в формате `+7 (495) 196-62-05`.

---

### Task 1: Таблица, миграция 0026, проверка полей

**Files:** Create `backend/migrations/versions/0026_organization_profile.py`, `backend/app/organization.py`; Modify `backend/app/models.py`; Test `backend/tests/test_organization.py`.

- [ ] Тест миграции: после `upgrade 0026` одна строка с данными владельца (все 9 полей), вторая вставка с `id=2` нарушает CHECK; `downgrade 0025` → `upgrade 0026` проходит.
- [ ] Модульные тесты `validate_ogrn('1095030001131')` проходит, `'1095030001132'` и `'12345'` — ошибка; `format_phone('+74951966205') == '+7 (495) 196-62-05'`.
- [ ] Реализация: модель `OrganizationProfile` (поля по спецификации, `CheckConstraint('id = 1', name='single_row')`), миграция с `op.bulk_insert`, `organization.py`: `OGRN_RE`, `validate_ogrn`, `format_phone`, `organization_name(db) -> str` (название или `'UniCRM'`, если строки нет).
- [ ] Прогон `tests/test_organization.py tests/test_migrations.py`, коммит.

### Task 2: API организации

**Files:** Create `backend/app/organization_routes.py`; Modify `backend/app/main.py` (роутер), `backend/tests/test_rbac.py` (публичный `GET /api/v1/organization/brand`); Test `backend/tests/test_organization.py`.

- [ ] Тесты: `GET` для `crm-user` отдаёт все поля (телефон в `phone` нормализован, `phone_display` отформатирован); `PUT` от `crm-user`/`crm-supervisor` — 403; `PUT` от `crm-admin` сохраняет и пишет `organization.update` с `{'fields': [...]}`; параметризованные 422: пустое название, неверный ОГРН, будущая дата, телефон `12`, email `bad`, адрес длиннее 500; `brand` без сессии → `{'name': 'ИТ Школа Ростелеком'}` и ничего больше.
- [ ] Реализация: `OrganizationIn` (pydantic, `extra='forbid'`, `strip_whitespace`), проверки ОГРН/даты/телефона в обработчике с русскими сообщениями, `OrganizationOut` с `phone_display`, `updated_at`.
- [ ] Прогон, полный набор, коммит.

### Task 3: Название в выгрузках и письмах

**Files:** Modify `backend/app/report_routes.py` (`_xlsx`, xls-построитель, `_pdf`, их вызовы), `backend/app/chart_routes.py` (`_header` + вызовы), `backend/app/email.py` (`from_name`), `backend/app/sender_addresses.py`, `backend/app/email_routes.py`; Test `backend/tests/test_reports.py`, `backend/tests/test_charts*.py`, `backend/tests/test_email.py`, `backend/tests/test_sender_requests.py`.

- [ ] Тесты: xlsx — `A1` = название организации, заголовки колонок во второй строке; xls — то же; PDF отчёта и графика содержит название (поиск текста в распакованном PDF или проверка вызова построителя с названием — выбрать способ, которым уже проверяются PDF в `test_reports.py`); после `PUT /organization` с новым названием выгрузка содержит новое; письмо подтверждения и тестовое письмо — `from_name` = название (без выбранного адреса) и последняя строка тела = название; `_http_sender` кладёт `from_name` в JSON; `_log_sender` пишет его.
- [ ] Реализация: построители принимают `organization: str`; `send_email(..., from_name=None)`; вызовы передают `organization_name(db)`. Существующие тесты с лямбдами без `**kwargs` обновить.
- [ ] Прогон, полный набор, коммит.

### Task 4: Страница «Организация»

**Files:** Create `frontend/src/api/organization.ts`, `frontend/src/pages/settings/OrganizationCard.tsx`; Modify `frontend/src/pages/settings/SettingsOrganizationPage.tsx`, `frontend/src/test/utils.tsx` (обработчики по умолчанию `GET /organization`, `GET /organization/brand`); Test `frontend/src/pages/settings/settingsOrganization.test.tsx`.

- [ ] Тесты: администратор меняет название и телефон → один `PUT` со всеми полями → «Изменения сохранены»; ошибка поля показывается у поля (`ogrn`); `crm-user` видит «ИТ Школа Ростелеком», ОГРН и телефон `+7 (495) 196-62-05` без полей ввода и без кнопки «Сохранить»; прежние тесты очереди адресов проходят.
- [ ] Реализация: `useOrganization`, `useUpdateOrganization` (обновляет кэш `organization` и `brand`), `OrganizationCard` (режим чтения / формы по ролям `crm-admin`/`crm-superadmin`), замена заглушки.
- [ ] tsc, eslint, vitest, коммит.

### Task 5: Название в меню и на экране входа

**Files:** Modify `frontend/src/app/Layout.tsx`, `frontend/src/app/AuthGate.tsx`, `frontend/src/api/organization.ts` (`useBrand`); Test `frontend/src/app/App.test.tsx` или новый `frontend/src/app/brand.test.tsx`.

- [ ] Тесты: после входа в боковом меню видно «ИТ Школа Ростелеком» под «UniCRM»; экран входа (сессии нет) показывает название; при ошибке `brand` экран входа работает без строки названия.
- [ ] Реализация: `useBrand` (`GET /organization/brand`, `staleTime` 5 мин, без повторов при 4xx), вывод второй строкой в `.brand` и `.auth-brand`; стили строки.
- [ ] tsc, eslint, vitest, build, коммит.

### Task 6: Документация и проверка

- [ ] `docs/api/organization.md`; запись D-227 в `docs/decisions.md` (карточка организации — одна строка, данные владельца в миграции, публичный `brand`, название в меню/входе/выгрузках/письмах).
- [ ] Полные наборы бэкенда и фронтенда, сборка; итоговая проверка всей ветки среза свежим ревьюером; исправления важных замечаний с тестами.
