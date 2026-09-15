# API загрузки справочников из xls/xlsx (контракт T-033)

Сценарий и правила разбора — `docs/design/import.md`. Доступ: руководитель (`crm-supervisor`) и администратор (`crm-admin`). Изменяющие запросы требуют `X-CSRF-Token`. Ошибки — `{code, message, details}`.

## Поля CRM

`GET /api/v1/imports/fields` → массив:

```json
[{"name": "university_name", "label": "Наименование вуза", "required": true}, …]
```

Порядок и состав полей: `university_name`, `vendor`, `software`, `contract_number`, `license_signed_at` (обязательные), `license_valid_until`, `transfer_status`, `manager_full_name`, `university_contacts`, `comment`, `it_directions`.

## Загрузить файл

`POST /api/v1/imports` — `multipart/form-data`, поле `file`.

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

`200` — `ImportReport` фактического результата. Корректные строки записываются одной транзакцией. Повторное применение — `409 CONFLICT`.

## Просмотр

- `GET /api/v1/imports/{id}` — объект как при загрузке (без `preview` строк старше 20), `status` = `uploaded` или `applied`, `report` — отчёт применения или `null`.
- `GET /api/v1/imports` — последние 20 загрузок: `[{id, filename, status, row_count, created_at, created_by, applied_at, summary | null}]`.
