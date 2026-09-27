# API администрирования (Настройки → Пользователи и роли)

Модель и решения — D-214–D-215 в `docs/decisions.md` и
`docs/design/account-roster-and-manager-access-2026-09-27.md`. Всё ниже доступно только роли
`crm-superadmin` (`403 FORBIDDEN` для любой другой роли, включая `crm-admin`).

## Все пользователи CRM

`GET /api/v1/admin/users` — читает действующие учётные записи Keycloak с ролью CRM. Поэтому
новый пользователь виден до первого входа. Локальная таблица CRM дополняет их датой последнего
входа; исторические строки без действующей записи Keycloak не показываются. Служебные и
ожидающие одобрения записи исключаются.

`200` — `{"available": true, "total": 5, "users": [{"keycloak_id", "username", "email", "full_name", "roles": [...], "is_active", "last_login_at"}, …]}`.
Если Keycloak Admin API не настроен: `{"available": false, "total": 0, "users": []}`.
Если настроен, но недоступен: `503 SERVICE_UNAVAILABLE`. Список читается постранично.

## Создать учётную запись

`POST /api/v1/admin/users` — создаёт менеджера или администратора. Пример:

```json
{"username":"admin_1","email":"admin_1@educrm-demo.ru","first_name":"Администратор","last_name":"Один","role":"crm-admin"}
```

`role` принимает только `crm-user` и `crm-admin`: через эту форму нельзя создать второго
руководителя или суперадминистратора. Сначала создаётся выключенная запись Keycloak, затем
назначается роль и сохраняется профиль CRM, после чего запись включается. Пароль генерируется
сервером, требуется его смена при первом входе. Он присутствует **только** в ответе `201`,
который помечен `Cache-Control: no-store`:

```json
{"keycloak_id":"...","username":"admin_1","email":"admin_1@educrm-demo.ru","role":"crm-admin","temporary_password":"..."}
```

Повтор логина или почты — `409 CONFLICT`; неверный формат или роль — `422 VALIDATION_ERROR`;
недоступный Keycloak — `503 SERVICE_UNAVAILABLE`. Ошибка после создания приводит к откату
незавершённой учётной записи. Пароль не хранится в CRM и не попадает в аудит. Новая локальная
запись CRM позволяет назначить сотруднику задачу до его первого входа.

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
состояние. Нет повышения роли существующего пользователя через интерфейс и нет выдачи новых ролей
`crm-supervisor`/`crm-superadmin`. Список заявок не постраничный — `list_users()` Keycloak Admin
API читает первые 200 учётных записей; для текущего размера реалма этого достаточно.
