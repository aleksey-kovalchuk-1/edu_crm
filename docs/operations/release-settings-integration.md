# Выпуск `ai/settings-integration` — чек-лист и откат

Ветка создана от рабочего `a42dc0c` (опубликованная аналитика не меняется). Новых миграций нет: рабочая база уже на `0028`. Выпуск — только после одобрения владельца.

## Уже проверено до выпуска (без изменения рабочей системы)

- Полные наборы: бэкенд на изолированной БД, фронтенд (tsc, eslint, vitest, сборка), сценарии резервного копирования и агента запросов, `plutil` для plist.
- Изолированный стенд `edu-crm-verify` (свой Keycloak, одноразовые учётные записи, после проверки удалён вместе с томами): все страницы «Настроек» под суперадминистратором; ручная копия в интерфейсе («Запрошена → Выполняется → Успешно») с настоящим агентом и поддельным исполнителем; завершение настоящего второго сеанса — второй браузер получает `401`, после перезагрузки видит форму пароля Keycloak, первый остаётся в системе; сценарии `keycloak-grant-admin-permissions.sh`, `keycloak-enable-login-events.sh`, `keycloak-add-middle-name.sh` на свежем realm.
- На рабочем Mac без изменения сервисов: `sid` сохраняется у входов после `0028`; служебная учётная запись получает `404` на удаление несуществующего сеанса (право есть); каталог запросов на фактическом пути монтирования (`deploy/local/backup-requests`, режим `700`, создан пустым) — контейнер uid 1000 создаёт флаг, повторный флаг отклоняется, агент забирает и удаляет.

## Перед выпуском

1. Одобрение владельца; слияние `ai/settings-integration` в рабочую ветку (ожидается перемотка вперёд от `a42dc0c`; если рабочая ветка ушла вперёд — остановиться и согласовать).
2. Записать точку отката: `git rev-parse HEAD` рабочей копии (ожидается `a42dc0c`) и пометить текущие образы:
   `docker image tag edu-crm-api edu-crm-api:rollback-a42dc0c && docker image tag edu-crm-web edu-crm-web:rollback-a42dc0c && docker image tag edu-crm-notifier edu-crm-notifier:rollback-a42dc0c`.
3. Убедиться, что версия базы `0028` (миграции при выпуске ничего не меняют): `docker compose exec -T db psql -U crm -d edu_crm -Atc 'select version_num from alembic_version'`.

## Выпуск

4. `scripts/deploy-public.sh` — создаёт зашифрованную пару копий перед выпуском, собирает и перезапускает `api`, `notifier`, `web`, проверяет вход.
5. `scripts/keycloak-add-middle-name.sh` (идемпотентен; если атрибут уже объявлен — «nothing to do»).

## Проверки после выпуска (smoke)

6. Вход суперадминистратором; «Настройки → Резервное копирование»: история пар как раньше и строка последнего запуска.
7. Права каталога запросов на живом контейнере: команда проверки из `docs/operations/backup.md` (создание флага из `api` и разбор агентом с поддельным исполнителем).
8. Установить агент запросов: скопировать `deploy/launchd/tech.unicrm.backup-request.plist` в `~/Library/LaunchAgents/`, `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/tech.unicrm.backup-request.plist`.
9. Проверка запуска через launchd и настоящей ручной копии: «Создать копию сейчас» → в течение минуты «Выполняется» → «Последний запуск ручной успешен», в истории новая «Ручная копия» с отметкой «Проверена»; лог `~/Library/Logs/edu-crm-backup-request.out.log`.
10. «Безопасность»: список сеансов и журнал Keycloak; при возможности — завершение второго сеанса.
11. Колокольчик уведомлений открывается; сервис `notifier` работает (`docker compose -f compose.yaml -f compose.public.yaml --profile notifications ps notifier`).

## Откат

- **Приложение** (новых миграций нет, база не откатывается): вернуть рабочую копию на `a42dc0c` и повторить `scripts/deploy-public.sh`, либо без пересборки вернуть образы: `docker image tag edu-crm-api:rollback-a42dc0c edu-crm-api` (так же `web`, `notifier`) и `docker compose -f compose.yaml -f compose.public.yaml --profile notifications up -d --no-deps api notifier web`. Монтирование каталога запросов уходит вместе с `compose.public.yaml` версии `a42dc0c`.
- **Агент запросов**: `launchctl bootout gui/$(id -u)/tech.unicrm.backup-request`, удалить `~/Library/LaunchAgents/tech.unicrm.backup-request.plist`; флаги в `deploy/local/backup-requests` удалить вручную (каталог можно оставить пустым).
- **Отчёт о запуске**: `last-run.json` рядом со `status.json` старая версия не читает — можно оставить; `status.json` не менялся.
- **Keycloak**: атрибут `middleName` безвреден и остаётся; удалять не нужно.
- **Данные**: при повреждении данных — восстановление из пары, созданной `deploy-public.sh`, в **новую** базу по `docs/operations/backup.md`; рабочую базу автоматически не заменять.
