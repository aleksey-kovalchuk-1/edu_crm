# Статус резервных копий

`GET /api/v1/admin/backups` доступен только роли `crm-superadmin`. Ответ содержит `available`, `reason`, `generated_at` и до 20 последних пар в `backups`. Для пары выдаются только время создания, тип (`source`), размеры зашифрованных копий базы и вложений и `verified` — прошла ли проверка расшифровки и чтения. Пути, имена архивов, их содержимое и ключ восстановления через API не передаются.

`available: false` означает, что метаданные ещё не настроены (`not_configured`), не созданы (`missing`) или временно недоступны (`unavailable`). Это не утверждение об отсутствии самих копий.

На рабочем сервере `scripts/deploy-public.sh` и `scripts/scheduled-backup.sh` публикуют очищенные метаданные только после создания обеих непустых зашифрованных копий. Ежедневная пара помечается `verified: true` после успешной проверки расшифровки и чтения; пара перед публикацией сохраняется с `verified: false`. API видит только каталог `deploy/local/backup-status` в режиме чтения. Архивы и ключ восстановления остаются вне контейнера API.

Отметка `verified` не означает, что было выполнено полное восстановление CRM из копии.

## Последний запуск и ручная копия

Ответ `GET /api/v1/admin/backups` не меняется. Рядом с ним (тоже только `crm-superadmin`):

- `GET /api/v1/admin/backups/run` → `{"available", "reason", "last_run", "pending_request", "pending_since", "manual_available"}`. `last_run` читается из `last-run.json`, который `scripts/scheduled-backup.sh` пишет через `scripts/record-backup-run.py` в тот же каталог статуса в начале и в конце **каждого** запуска, включая неудачные (`result`: `running`, `success`, `failure`, `interrupted` — отчёт `running` старше 6 часов; `error` — этап: `preflight_failed`, `database_backup_failed`, `attachments_backup_failed`, `verification_failed`, `retention_failed`, `status_record_failed`). `last_run: null` — запусков ещё не было; `reason: "unavailable"` — отчёт не читается. `pending_request` — запрос ждёт или уже взят агентом; `pending_since` — с какого момента.
- `POST /api/v1/admin/backups/manual` → `202 {"state": "requested"}`. Создаёт `request.json` в `BACKUP_REQUEST_DIR` (атомарно, `O_EXCL`); `409`, если запрос уже ждёт или копия выполняется; `503`, если каталог запросов не настроен. LaunchAgent `tech.unicrm.backup-request` запускает `scripts/run-requested-backup.sh`: тот забирает флаг (переименованием, ссылки не выполняются и не разыменовываются), игнорирует его содержимое и запускает тот же `scheduled-backup.sh` с меткой `manual-YYYYMMDD-HHMMSS`. Пара появляется в истории как «Ручная копия»; ручные копии автоматически не удаляются. Событие журнала `backup.manual_requested`.

Страница показывает предупреждение, если новейшая пара старше 36 часов, итог последнего запуска и состояние ручного запроса; если запрос не взят за 5 минут — «Служба копирования не отвечает».
