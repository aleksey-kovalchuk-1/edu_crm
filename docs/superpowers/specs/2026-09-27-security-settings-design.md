# Настройки → Безопасность

Срез 4 из 5 запроса «Настройки» от 27.09.2026. Согласовано с владельцем 27.09.2026: история входов — входы в CRM плюс журнал событий Keycloak (хранение событий включается при выпуске).

## Мои сеансы

- Источник: собственные сеансы CRM (`sessions`) текущего пользователя, не завершённые и не истёкшие. Показываются браузер и ОС (разбор User-Agent), IP, начало, последняя активность (`validated_at`), отметка «Это устройство».
- Публичный идентификатор сеанса — `sha256('public:' + sessions.id)[:16]`; ни токены, ни `sessions.id` в ответах не появляются.
- Завершение: чужой сеанс — `404`; текущий — `409` («Для текущего устройства используйте «Выйти»»); иначе `revoked_at = now` и, если у сеанса известен `keycloak_session_id` и он не совпадает с сеансом Keycloak текущего устройства, `DELETE /admin/realms/edu-crm/sessions/{sid}`. Если Keycloak недоступен или сеанс старый (без `sid`), сеанс CRM всё равно завершается, а ответ сообщает: «Сеанс Keycloak завершится сам после 30 минут бездействия».
- «Завершить все остальные» — то же для всех сеансов, кроме текущего.
- Миграция `0028`: `sessions.keycloak_session_id varchar(64)`; при входе сохраняется утверждение `sid` из ID-токена.

## История входов

- Входы в CRM: сеансы пользователя за 30 дней, до 50 записей: время, IP, устройство, состояние (активен / завершён / истёк).
- Журнал Keycloak: `GET /admin/realms/edu-crm/events?user={keycloak_sub}&type=LOGIN&type=LOGIN_ERROR&type=LOGOUT&type=UPDATE_PASSWORD&max=50`. Доступен, только если в realm `eventsEnabled = true` и у служебной учётной записи есть `view-events`; иначе ответ `{"available": false, "reason": ...}` и интерфейс пишет «Журнал Keycloak недоступен: хранение событий не включено» (или «недоступен сейчас» при сбое связи) — пустой список как «событий не было» не показывается.
- `scripts/keycloak-enable-login-events.sh` (идемпотентный, через `kcadm`): `eventsEnabled=true`, `eventsExpiration=2592000` (30 дней), `enabledEventTypes=[LOGIN, LOGIN_ERROR, LOGOUT, UPDATE_PASSWORD]`, роль `view-events` служебной учётной записи и её scope-mapping. Те же настройки — в `deploy/keycloak/realm-edu-crm.json`; `view-events` — в `scripts/keycloak-grant-admin-permissions.sh`. Запуск против рабочего realm — только при выпуске с разрешения владельца. События копятся с момента включения.

## Парольная политика

- Читается из Keycloak (`passwordPolicy`, `bruteForceProtected`, `failureFactor`) и показывается по-русски: `length(n)` → «Не короче n символов», `maxLength(n)` → «Не длиннее n символов», `notUsername` → «Не совпадает с логином», `notEmail` → «Не совпадает с email», `passwordHistory(n)` → «Не повторяет последние n паролей», `digits(n)` → «Содержит цифр: не меньше n», `upperCase(n)`, `lowerCase(n)`, `specialChars(n)` — аналогично, `forceExpiredPasswordChange(n)` → «Меняется каждые n дней»; неизвестное правило показывается как есть. При `bruteForceProtected` — «После {failureFactor} неудачных попыток вход временно блокируется».
- Всем: ссылка «Сменить пароль» на личный кабинет Keycloak (`{OIDC_ISSUER}/account/account-security/signing-in`). CRM паролей не хранит.
- `crm-admin`/`crm-superadmin`: ссылка «Изменить политику в Keycloak» на консоль администратора (`…/auth/admin/master/console/#/edu-crm/authentication/policies`) с пояснением, что нужна учётная запись администратора Keycloak. В CRM политика не меняется.
- Если клиент администрирования Keycloak не настроен или недоступен — «Политика недоступна», без выдуманных правил.

## API

Только свои данные, любая роль CRM (и `crm-superadmin`): `GET /security/sessions`, `DELETE /security/sessions/{public_id}`, `POST /security/sessions/terminate-others`, `GET /security/login-history`, `GET /security/password-policy`.

## Проверка

Бэкенд: только свои сеансы; чужой — `404`, текущий — `409`; завершение закрывает сеанс Keycloak и не закрывает общий с текущим устройством; сбой Keycloak не мешает завершению сеанса CRM; в ответах нет токенов и `sessions.id`; история Keycloak — доступна / выключена / сбой; разбор каждого правила политики. Фронтенд: завершение сеанса и «все остальные», сообщение о недоступности журнала, список правил, ссылка для администратора только администратору.
