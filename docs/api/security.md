# API безопасности

Спецификация: `docs/superpowers/specs/2026-09-27-security-settings-design.md`; решение D-229. Все методы — только для своих данных, любая роль CRM (и `crm-superadmin`). Токены и ключи сеансов в ответы не попадают: сеанс обозначается необратимым `id` (`sha256('public:' + ключ)[:16]`).

## Сеансы

- `GET /api/v1/security/sessions` — активные сеансы CRM (не завершены, не истекли): `{"id", "device", "ip", "created_at", "last_active_at", "current"}`; `device` — браузер и ОС из User-Agent или «Неизвестное устройство».
- `DELETE /api/v1/security/sessions/{id}` → `{"keycloak_ended", "message"}`. Чужой или неизвестный — `404`; текущий — `409` («Для текущего устройства используйте «Выйти»»). Сеанс CRM завершается всегда; сеанс Keycloak (`sid`, сохраняется при входе с миграции `0028`) завершается, если он известен, не общий с текущим устройством и Keycloak доступен — иначе сообщение: «Сеанс Keycloak завершится сам после 30 минут бездействия».
- `POST /api/v1/security/sessions/terminate-others` → `{"count", "keycloak_all_ended", "message"}`.

## История входов

`GET /api/v1/security/login-history` → `{"crm": [{"at", "device", "ip", "state": "active"|"ended"|"expired"}], "keycloak": {"available", "reason", "events": [{"at", "type", "label", "ip", "error"}]}}`. CRM — сеансы за 30 дней (до 50). Keycloak — события `LOGIN`, `LOGIN_ERROR`, `LOGOUT`, `UPDATE_PASSWORD` (до 50, новые сверху); `reason`: `not_configured` (нет клиента администрирования), `disabled` (хранение событий выключено или нет `view-events`), `unavailable` (сбой связи). Хранение включает `scripts/keycloak-enable-login-events.sh` (30 дней, `view-events` служебной учётной записи) — при выпуске; события копятся с момента включения.

## Парольная политика

`GET /api/v1/security/password-policy` → `{"available", "rules", "brute_force", "change_password_url", "admin_console_url"}`. `rules` — правила Keycloak по-русски (неизвестные — как есть), `brute_force` — «После N неудачных попыток вход временно блокируется». `change_password_url` — личный кабинет Keycloak; `admin_console_url` — только для `crm-admin`/`crm-superadmin` (изменение политики — в консоли Keycloak учётной записью администратора Keycloak). Без связи с Keycloak — `available: false`, правил нет.
