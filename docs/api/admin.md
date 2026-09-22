# API администрирования (Настройки → Пользователи и роли)

Модель и решения — D-214–D-215 в `docs/decisions.md`. Всё ниже доступно только роли
`crm-superadmin` (`403 FORBIDDEN` для любой другой роли, включая `crm-admin`). Простая модель
прав проекта: один суперадминистратор, остальные — обычные пользователи CRM, пока их не повысят
вручную (эта возможность здесь пока не реализована — см. «Что не реализовано» ниже).

## Все пользователи CRM

`GET /api/v1/admin/users` — читает собственную таблицу `users` (не Keycloak напрямую).

`200` — `{"total": 12, "users": [{"id", "email", "full_name", "roles": [...], "is_active", "created_at", "last_login_at"}, …]}`.

## Заявки на доступ («pending registrations»)

`GET /api/v1/admin/pending-registrations` — заявка на доступ это учётная запись Keycloak, которая
уже может войти в систему, но не имеет ни одной роли CRM (`crm-user`/`crm-supervisor`/`crm-admin`/
`crm-superadmin`) — значит, локальная запись `users` для неё ещё не создана и доступа внутри CRM
у неё нет. Список получается напрямую из Keycloak Admin API (`app.state.keycloak_admin`), учётные
записи без email (например, служебная запись `edu-crm-admin`) исключаются.

`200` — `{"available": true | false, "pending": [{"keycloak_id", "email", "username"}, …]}`.
`available: false` (с пустым `pending`), если в этом окружении не заданы
`KEYCLOAK_ADMIN_CLIENT_ID`/`KEYCLOAK_ADMIN_CLIENT_SECRET` — это состояние «данные недоступны», а не
«заявок нет», интерфейс обязан показывать его отдельно (D-214).

Ошибка: Keycloak временно недоступен — `503 SERVICE_UNAVAILABLE`.

## Одобрить заявку

`POST /api/v1/admin/pending-registrations/{keycloak_id}/approve` — без тела запроса. Выдаёт ровно
одну роль `crm-user` через `KeycloakAdminClient.assign_realm_role` — действие пишется в журнал
действий (`admin.pending_registration_approve`).

`204`. Ошибки: Keycloak Admin API не настроен или запрос отклонён Keycloak — `503 SERVICE_UNAVAILABLE`.

## Что не реализовано (сознательно, D-215)

Нет отдельного действия «отклонить» — неодобренная заявка и так не даёт доступа, это то же самое
состояние. Нет повышения роли (до supervisor/admin/superadmin) — по спецификации проекта это
отдельная, ещё не реализованная возможность. Список заявок не постраничный — `list_users()`
Keycloak Admin API читает первые 200 учётных записей; для текущего размера реалма этого достаточно.
