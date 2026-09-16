# API загрузки справочников из xls/xlsx (T-033, обобщено в T-091/T-092)

Сценарий и правила разбора договоров — `docs/design/import.md`; обобщённый импорт по сущностям и фоновая модель — `docs/design/file-ingestion-plan.md` §3.1/§3.2, решения D-166, D-167, D-172 в `docs/decisions.md`. Изменяющие запросы требуют `X-CSRF-Token`. Ошибки — `{code, message, details}`.

## Сущности

Каждый запрос указывает `entity`: `universities`, `university_contacts`, `interactions` (только создание — обновление статуса взаимодействия через импорт не предусмотрено, D-167) или `contracts` (исходный поток T-033, поведение не изменилось). Без параметра — по умолчанию `contracts`, для обратной совместимости.

| Сущность | Доступ | Идентичность строки (создание/обновление) |
|---|---|---|
| `universities` | руководитель, администратор (как создание вуза через API) | название вуза |
| `university_contacts` | все роли, в пределах области видимости | (вуз, ФИО); вуз должен уже существовать |
| `interactions` | все роли, в пределах области видимости | только создание; повтор (вуз, программа, ответственный, срок) внутри файла — последняя строка |
| `contracts` | руководитель, администратор | номер договора (без изменений, T-033) |

`universities`/`university_contacts`/`interactions` применяются **фоновой задачей** (`202`, см. ниже); `contracts` — синхронно, как раньше (`200`).

## Поля CRM

`GET /api/v1/imports/fields?entity=` → массив:

```json
[{"name": "university_name", "label": "Наименование вуза", "required": true}, …]
```

Для `contracts` состав не изменился (см. ниже). Для остальных сущностей — свой набор полей, тем же способом (синонимы заголовков без учёта регистра).

## Загрузить файл

`POST /api/v1/imports` — `multipart/form-data`, поле `file`, поле `entity` (по умолчанию `contracts`). Неизвестная сущность — `422 VALIDATION_ERROR` (`details[].field = "entity"`). Ответ `ImportOut` теперь несёт `entity`.

`201`:

```json
{
  "id": 4,
  "filename": "реестр.xlsx",
  "status": "uploaded",
  "header_row": 2,
  "headers": ["Наименование вуза", "Вендор", "ИТ-продукт", "№ договора", "Дата подписания"],
  "mapping": {"university_name": "Наименование вуза", "vendor": "Вендор", "software": "ИТ-продукт", "contract_number": "№ договора", "license_signed_at": "Дата подписания", "license_valid_until": null, "transfer_status": null, "manager_full_name": null, "university_contacts": null, "comment": null, "it_directions": null},
  "row_count": 128,
  "preview": [{"row_number": 3, "cells": ["Волжский институт цифровых технологий", "РТК ИТ", "Учебная среда", "Д-001", "2026-01-15"]}],
  "created_at": "2026-09-16T02:10:00Z",
  "created_by": {"id": 2, "full_name": "Павел Демо"},
  "report": null
}
```

- `preview` — первые 20 строк данных; `cells` в порядке `headers`; даты — `YYYY-MM-DD`, пустые ячейки — `null`.
- `mapping` — предложенное сопоставление «поле CRM → заголовок столбца».
- Ошибки: файл больше 10 МБ — `413 PAYLOAD_TOO_LARGE`; не Excel — `415 UNSUPPORTED_MEDIA_TYPE`; файл повреждён, пуст или слишком много строк — `422 VALIDATION_ERROR` с `details: [{"field": "file", "message": "…"}]`.

## Проверить без записи

`POST /api/v1/imports/{id}/check` — тело `{"mapping": {поле: заголовок | null}}`.

`200` — `ImportReport`:

```json
{
  "summary": {
    "rows": 128, "valid": 125, "invalid": 2, "skipped": 1, "with_warnings": 9,
    "created": {"universities": 3, "it_products": 2, "it_directions": 1, "university_contacts": 14, "contracts": 110},
    "updated": {"contracts": 15}
  },
  "rows": [
    {"row_number": 3, "status": "ok", "action": "create", "contract_number": "Д-001", "errors": [], "warnings": []},
    {"row_number": 9, "status": "warning", "action": "update", "contract_number": "Д-007", "errors": [], "warnings": ["Менеджер «Анна Демо» не найден среди пользователей CRM; ФИО сохранено текстом"]},
    {"row_number": 17, "status": "error", "action": null, "contract_number": "", "errors": ["Не заполнено поле «Номер договора»"], "warnings": []}
  ]
}
```

- `status`: `ok`, `warning` (будет записана с замечаниями), `error` (будет пропущена), `skipped` (повтор номера договора ниже в файле).
- `action`: `create`, `update` или `null`.
- Ошибки сопоставления (не выбрано обязательное поле, столбец отсутствует, один столбец для двух полей) — `422 VALIDATION_ERROR` с `details: [{"field": "mapping", "message": "…"}]`.

## Применить

`POST /api/v1/imports/{id}/apply` — тело `{"mapping": …}`.

- `contracts`: без изменений — `200` с `ImportReport` фактического результата, запись одной транзакцией.
- `universities` / `university_contacts` / `interactions`: `202` — `{"job_id": 42, "status": "queued"}`. Запись выполняется фоновой задачей (все-или-ничего, одна транзакция на файл); статус — `GET /api/v1/jobs/{job_id}` (общий эндпоинт для всех фоновых задач, включая будущие отчёты). Повторный `apply` при уже стоящей в очереди/выполняющейся задаче возвращает тот же `job_id`, а не создаёт вторую задачу; уже применённая загрузка — `409 CONFLICT`.

`BackgroundJob.result` для `import_apply` — тот же `ImportReport`, что раньше возвращался синхронно; смотрите его через `GET /api/v1/jobs/{job_id}` после завершения (`status = "succeeded"`).

## Откатить (T-092)

`POST /api/v1/imports/{id}/rollback` — только для `universities`/`university_contacts`/`interactions` (`contracts` — `409 CONFLICT`, откат не поддерживается) и только для уже применённой загрузки. `202` — `{"job_id": …, "status": "queued"}`. «Безопасный» откат: строки, изменённые после импорта (по журналу действий), не откатываются и помечаются в результате `not_rolled_back` с причиной; остальные создания и обновления отменяются. Результат — в `GET /api/v1/jobs/{job_id}` после завершения: `[{"entity", "record_id", "status": "rolled_back" | "not_rolled_back", "reason"}]`.

## Отчёт об ошибках

`GET /api/v1/imports/{id}/errors.xlsx` — файл xlsx со столбцами «Строка», «Тип» (Ошибка/Предупреждение), «Сообщение» по последнему отчёту (проверки или применения). `409 CONFLICT`, если отчёта ещё нет.

## Сохранённые сопоставления

`GET /api/v1/import-mappings?entity=` — список `{id, entity, name, mapping, created_by, created_at}`. `POST /api/v1/import-mappings` — `{"entity", "name", "mapping"}`; повтор `(entity, name)` — `409 CONFLICT`.

## Просмотр

- `GET /api/v1/imports/{id}` — объект как при загрузке (без `preview` строк старше 20), `status` = `uploaded` или `applied`, `entity`, `report` — отчёт применения или `null`.
- `GET /api/v1/imports` — последние 20 загрузок: `[{id, filename, status, row_count, created_at, created_by, applied_at, summary | null}]`.

## Фоновые задачи

`GET /api/v1/jobs/{id}` — `{id, kind, status, payload, result, error, correlation_id, created_by, created_at, started_at, finished_at}`. `status`: `queued`, `running`, `succeeded`, `failed`. Задача видна её создателю; руководителю и администратору — любая (как в остальном API, D-141). Чужая или несуществующая задача — `404 RECORD_NOT_FOUND`.
