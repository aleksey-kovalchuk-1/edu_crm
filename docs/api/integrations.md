# Граница интеграции LMS и сайта (предварительно)

> **Внутренний пример, не контракт заказчика.** Контракты LMS и сайта ИТ Школы ещё не получены (D-233, D-246).
> Ничего не сохраняется и не используется в процессах, отчётах и аналитике.

Все методы доступны роли `crm-admin` (и `crm-superadmin`, которая её включает); остальные роли получают `403`,
без входа — `401`. Методы `POST` требуют заголовок `X-CSRF-Token`, как и остальной API. Как будут
аутентифицироваться сами LMS и сайт, определит контракт.

## Описание формата

`GET /api/v1/integrations/contracts` → `200`:

```json
{
  "preliminary": true,
  "customer_contract": false,
  "notice": "Внутренний пример, не контракт заказчика. …",
  "schema_version": "0.1-preliminary",
  "stores_data": false,
  "record_schema": {"…": "JSON Schema записи"},
  "sources": {
    "lms": {"status": "awaiting_customer_contract", "endpoint": "/api/v1/integrations/lms", "examples": [{"preliminary": true, "title": "…", "record": {"…": "…"}}]},
    "website": {"status": "awaiting_customer_contract", "endpoint": "/api/v1/integrations/website", "examples": ["…"]}
  }
}
```

## Заглушки приёма

`POST /api/v1/integrations/lms` и `POST /api/v1/integrations/website`, тело — одна запись:

```json
{
  "schema_version": "0.1-preliminary",
  "source": "lms",
  "external_id": "lms-example-0001",
  "occurred_at": "2026-09-29T09:30:00+03:00",
  "event_type": "enrollment",
  "university_ref": "example-university",
  "program_ref": "example-program"
}
```

`200` — запись прошла проверку и **не сохранена**:

```json
{"status": "validated_only", "stored": false, "preliminary": true,
 "message": "Запись соответствует предварительному внутреннему формату и не сохранена: контракт заказчика ещё не утверждён.",
 "record": {"…": "запись, время в UTC"}}
```

`422 VALIDATION_ERROR` — нет обязательного поля, лишнее поле (например, `raw_payload`), неверное значение,
время без часового пояса или запись другого источника (`source` не совпадает с адресом).

Поля и предварительное сопоставление описаны в [`docs/design/lms-cms-mocks.md`](../design/lms-cms-mocks.md).
