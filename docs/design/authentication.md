# Аутентификация и сессии (Keycloak)

Статус: проект для задач T-020–T-024. Решения — D-104, D-117, D-118, D-122–D-126 в `docs/decisions.md`.

## Цели

- Вход только через Keycloak (требование спецификации); собственных паролей в CRM нет.
- Токены Keycloak не попадают в JavaScript браузера.
- Отключение пользователя или завершение его сессии в Keycloak прекращает доступ к CRM в течение нескольких минут.
- Работает при нескольких процессах API (любой процесс может завершить вход).

## Компоненты

| Компонент | Роль |
|---|---|
| Keycloak `26.7.3` (режим `start`, БД `keycloak` в PostgreSQL) | Учётные записи, пароли, роли `crm-user`, `crm-supervisor`, `crm-admin`, защита от перебора |
| nginx (`:8080`) | Единая точка входа: `/` — интерфейс, `/api/` — API, `/auth/` — Keycloak |
| API (FastAPI) | Конфиденциальный OIDC-клиент `edu-crm-api`: код авторизации + PKCE S256; хранит сессии в PostgreSQL |
| Браузер | Получает только cookie `edu_crm_session` (HttpOnly, SameSite=Lax) и CSRF-токен |

Keycloak публикуется через nginx по пути `/auth`, поэтому издатель токенов (`iss`) стабилен: `http://localhost:8080/auth/realms/edu-crm`. API обращается к Keycloak напрямую по сети Compose (`http://keycloak:8080/auth`) — включён `KC_HOSTNAME_BACKCHANNEL_DYNAMIC`.

## Поток входа

1. Интерфейс получает `401 UNAUTHENTICATED` и перенаправляет браузер на `GET /api/v1/auth/login?next=<путь>`.
2. API создаёт запись `login_states` (хэш `state`, `nonce`, `code_verifier`, путь возврата, срок 10 минут) и перенаправляет на страницу входа Keycloak.
3. Keycloak возвращает браузер на `GET /api/v1/auth/callback?code&state`.
4. API однократно использует `state` (запись удаляется), обменивает код на токены (секрет клиента + `code_verifier`), проверяет ID-токен: подпись по JWKS, `iss`, `aud`, срок действия, `nonce`.
5. Из токена берутся `sub`, `email`, `name` и роли `crm-*` (встроенные роли Keycloak отбрасываются). Запись `users` создаётся или обновляется.
6. Создаётся сессия: в БД хранится SHA-256 от случайного токена, CSRF-токен, срок, IP и User-Agent, а также refresh-токен Keycloak в зашифрованном виде (ключ `SESSION_ENCRYPTION_KEY`).
7. Браузер получает cookie и перенаправляется на путь возврата. Разрешены только относительные пути внутри приложения (защита от открытого редиректа).

## Проверка сессии на каждом запросе

- Cookie → хэш → действующая, не отозванная сессия активного пользователя; иначе `401 UNAUTHENTICATED`.
- Если с последней сверки с Keycloak прошло больше 120 секунд, API обновляет токены по refresh-токену. Ошибка (`invalid_grant`, пользователь отключён, сессия Keycloak завершена) отзывает сессию CRM → `401`. Роли обновляются из нового токена.
- Изменяющие запросы (`POST`, `PUT`, `PATCH`, `DELETE`) требуют заголовок `X-CSRF-Token`, совпадающий с токеном сессии, и допустимый `Origin`, если он передан; иначе `403 FORBIDDEN`.

## Выход

`POST /api/v1/auth/logout` отзывает сессию, удаляет cookie и возвращает адрес завершения сессии Keycloak (`end_session_endpoint` с `client_id` и `post_logout_redirect_uri`), на который переходит интерфейс.

## API

| Метод | Назначение |
|---|---|
| `GET /api/v1/auth/login?next=` | Начать вход |
| `GET /api/v1/auth/callback` | Завершить вход |
| `GET /api/v1/auth/me` | Текущий пользователь, роли и CSRF-токен |
| `POST /api/v1/auth/logout` | Выйти |

## Таблицы

- `users`: `id`, `keycloak_sub` (уникальный), `email`, `full_name`, `roles` (кэш ролей `crm-*`), `is_active`, `created_at`, `last_login_at`.
- `sessions`: `id` (SHA-256 токена), `user_id`, `csrf_token`, `refresh_token_encrypted`, `created_at`, `expires_at`, `validated_at`, `revoked_at`, `ip`, `user_agent`.
- `login_states`: `state_hash`, `nonce`, `code_verifier`, `next_path`, `created_at`, `expires_at`.

## Тестирование

Тесты не обращаются к настоящему Keycloak: генерируется RSA-ключ, JWKS и ответы token-endpoint подставляются через `httpx.MockTransport`. Проверяются: успешный вход, повторное использование `state`, неверные `iss`/`aud`/`nonce`/подпись, просроченная сессия, отзыв при неудачном обновлении, фильтрация ролей, CSRF и `Origin`, открытый редирект. Сквозной вход через настоящий Keycloak проверяется в браузере на стенде Docker Compose.
