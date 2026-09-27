# Настройки → Безопасность — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Сеансы с безопасным завершением, история входов (CRM + Keycloak), парольная политика из Keycloak.

**Architecture:** Миграция `0028` (`sessions.keycloak_session_id`), `sid` сохраняется при входе; `KeycloakAdminClient` получает `delete_session`, `list_user_events`, `get_realm_security`; `app/security_routes.py` — API; `app/password_policy.py` — перевод правил; скрипт включения событий; страница «Безопасность».

**Spec:** `docs/superpowers/specs/2026-09-27-security-settings-design.md`

## Global Constraints
- Ветка `ai/profile-senders`; миграция `revision='0028'`, `down_revision='0027'`.
- Никаких токенов и `sessions.id` в ответах; только свои данные.
- Скрипты против рабочего Keycloak не запускать; не пушить, не выпускать.
- Тесты — изолированная БД `127.0.0.1:55432`.

## Review Focus
- Сеанс, у которого `sid` совпадает с текущим устройством — не завершать сеанс Keycloak.
- Старые сеансы без `sid` — завершаются только в CRM, с честным сообщением.
- Keycloak не настроен (локальная разработка) — сеансы работают, журнал и политика «недоступны».
- User-Agent пустой или неизвестный — «Неизвестное устройство».
- Истёкшие, но не отозванные сеансы — не в списке активных, в истории «истёк».

### Task 1: sid при входе и миграция 0028
- [ ] Тесты: вход сохраняет `sid` из ID-токена; round-trip миграции. Реализация: `Identity.session_id`, колонка, запись при создании сеанса. Коммит.

### Task 2: Клиент Keycloak
- [ ] Тесты (фейк): `delete_session`, `list_user_events` (403 → недоступно), `get_realm_security`. Реализация, эндпоинты фейка. Коммит.

### Task 3: Правила политики
- [ ] Тесты разбора всех правил и неизвестного; реализация `app/password_policy.py`. Коммит.

### Task 4: API безопасности
- [ ] Тесты по спецификации (сеансы, завершение, история, политика, отсутствие секретов). Реализация `app/security_routes.py`. Коммит.

### Task 5: Включение журнала Keycloak
- [ ] `scripts/keycloak-enable-login-events.sh`, `view-events` в скрипте прав, настройки в realm JSON; проверка `bash -n` и корректности JSON. Коммит.

### Task 6: Страница «Безопасность»
- [ ] Тесты фронтенда; реализация страницы. Коммит.

### Task 7: Документация и проверка
- [ ] `docs/api/security.md`, D-229; полные наборы; свежий ревьюер; исправления.
