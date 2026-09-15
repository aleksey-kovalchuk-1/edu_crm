# API справочников и договоров (контракт T-031)

Модель данных и правила — `docs/design/catalogs.md`. Все ответы с ошибками — `{code, message, details}` (`docs/api/errors.md`). Все изменяющие запросы требуют `X-CSRF-Token`. Роли: `crm-user` — менеджер, `crm-supervisor` — руководитель, `crm-admin` — администратор.

## Общие правила

- **Область видимости менеджера:** менеджер видит и изменяет только вузы, где он назначен ответственным (`university_managers`), и связанные с ними контакты, договоры, взаимодействия и задачи. Запись вне области видимости — `404 RECORD_NOT_FOUND` (существование не раскрывается). Руководитель и администратор видят всё.
- **Списки с пагинацией** возвращают `{"items": [...], "total": 123, "limit": 50, "offset": 0}`; параметры `limit` (1–200, по умолчанию 50) и `offset` (≥ 0).
- **Неактивные записи** справочников скрыты, если не передан `include_inactive=true`.
- **Поиск** `q` — подстрока без учёта регистра.
- **Дубликаты** уникальных значений — `409 CONFLICT`, в `details` указано поле.
- Даты — `YYYY-MM-DD`; время — ISO 8601 в UTC.

## ИТ-направления

| Метод и путь | Роли | Описание |
|---|---|---|
| `GET /api/v1/it-directions?q=&include_inactive=` | все | Массив `ITDirection` по алфавиту |
| `POST /api/v1/it-directions` | руководитель, администратор | Тело `{name, description?}` → `201 ITDirection` |
| `PATCH /api/v1/it-directions/{id}` | руководитель, администратор | Тело `{name?, description?, is_active?}` → `ITDirection` |

`ITDirection`: `{"id": 1, "name": "DevOps", "description": "", "is_active": true}`

## ИТ-продукты

| Метод и путь | Роли | Описание |
|---|---|---|
| `GET /api/v1/it-products?q=&direction_id=&include_inactive=` | все | Массив `ITProduct` по вендору и названию |
| `POST /api/v1/it-products` | руководитель, администратор | Тело `{vendor, name, description?, direction_ids?: number[]}` → `201 ITProduct` |
| `PATCH /api/v1/it-products/{id}` | руководитель, администратор | Тело `{vendor?, name?, description?, direction_ids?, is_active?}` → `ITProduct` |

`ITProduct`: `{"id": 3, "vendor": "РТК ИТ", "name": "Учебная среда", "description": "", "is_active": true, "directions": [{"id": 1, "name": "DevOps"}]}`

## Учебные заведения

| Метод и путь | Роли | Описание |
|---|---|---|
| `GET /api/v1/universities?q=&include_inactive=` | все (в области видимости) | Массив `University` по названию |
| `POST /api/v1/universities` | руководитель, администратор | Тело `{name, city, short_name?, region?, website?, contact?}` → `201 University` |
| `PATCH /api/v1/universities/{id}` | руководитель, администратор | Те же поля и `is_active` → `University` |
| `PUT /api/v1/universities/{id}/managers` | руководитель, администратор | Тело `{user_ids: number[]}` — полный список ответственных → `University` |

`University`: `{"id": 1, "name": "Северный технологический университет", "short_name": "СТУ", "city": "Санкт-Петербург", "region": "", "website": "", "contact": "", "is_active": true, "managers": [{"id": 5, "full_name": "Анна Демо"}]}`

## Пользователи CRM (для назначения ответственных)

| Метод и путь | Роли | Описание |
|---|---|---|
| `GET /api/v1/users?role=crm-user` | руководитель, администратор | Массив `{id, full_name, email, roles, is_active}` активных пользователей по имени |

Пользователь появляется в CRM после первого входа через Keycloak.

## Контакты вуза (ответственные от вуза)

| Метод и путь | Роли | Описание |
|---|---|---|
| `GET /api/v1/universities/{id}/contacts?include_inactive=` | все (в области видимости) | Массив `UniversityContact` по ФИО |
| `POST /api/v1/universities/{id}/contacts` | все (в области видимости) | Тело `{full_name, position?, email?, phone?, comment?}` → `201 UniversityContact` |
| `PATCH /api/v1/university-contacts/{id}` | все (в области видимости) | Те же поля и `is_active` → `UniversityContact` |

`UniversityContact`: `{"id": 7, "university_id": 1, "full_name": "Иван Демо", "position": "Проректор", "email": "", "phone": "", "comment": "", "is_active": true}`

## Договоры и лицензии

| Метод и путь | Роли | Описание |
|---|---|---|
| `GET /api/v1/contracts` | все (в области видимости) | Список с пагинацией `Contract`; фильтры ниже |
| `GET /api/v1/contracts/transfer-statuses` | все | `[{"value": "not_started", "label": "Не начата"}, …]` |
| `GET /api/v1/contracts/{id}` | все (в области видимости) | `Contract` |
| `POST /api/v1/contracts` | все (в области видимости) | Тело `ContractInput` → `201 Contract` |
| `PATCH /api/v1/contracts/{id}` | все (в области видимости) | Любые поля `ContractInput` → `Contract` |

Фильтры `GET /api/v1/contracts`: `q` (номер договора, вуз, продукт, вендор), `university_id`, `it_product_id`, `it_direction_id`, `manager_user_id`, `transfer_status`, `signed_from`, `signed_to`, `valid_until_to`, `sort` (`signed_at`, `-signed_at`, `valid_until`, `-valid_until`, `contract_number`; по умолчанию `-signed_at`), `limit`, `offset`.

`ContractInput`: `{contract_number, university_id, it_product_id, signed_at, valid_until?, transfer_status?, manager_user_id?, contact_ids?: number[], comment?}`
- `valid_until` не передан → подписание + 1 год.
- Менеджер может указать вуз только из своей области видимости; если `manager_user_id` не передан, для менеджера подставляется он сам.
- `contact_ids` должны принадлежать тому же вузу, иначе `422 VALIDATION_ERROR`.

`Contract`:

```json
{
  "id": 12,
  "contract_number": "Д-2026-001",
  "university": {"id": 1, "name": "Северный технологический университет"},
  "it_product": {"id": 3, "vendor": "РТК ИТ", "name": "Учебная среда"},
  "signed_at": "2026-01-15",
  "valid_until": "2027-01-15",
  "transfer_status": "in_progress",
  "transfer_status_label": "Идёт передача",
  "manager": {"id": 5, "full_name": "Анна Демо"},
  "manager_name": "",
  "contacts": [{"id": 7, "full_name": "Иван Демо"}],
  "comment": "",
  "is_expired": false,
  "expires_soon": false,
  "updated_at": "2026-09-16T01:20:00Z"
}
```

`expires_soon` — срок действия истекает в ближайшие 30 дней; `is_expired` — срок уже истёк.
