# API процессов, статусов и вложений

Модель и правила — `docs/design/workflows.md`, решения D-149–D-154. Интерактивное описание — Swagger `/api/docs`, раздел «Процессы и статусы». Коды ошибок — `docs/api/errors.md`.

Все запросы выполняются в сессии Keycloak; изменяющие запросы требуют заголовок `X-CSRF-Token`.

## Процессы

| Метод и путь | Роли | Ответ |
|---|---|---|
| `GET /api/v1/workflows` | все | `WorkflowOut[]`, базовый процесс первым |
| `POST /api/v1/workflows` | руководитель, администратор | 201 `WorkflowOut` |
| `PATCH /api/v1/workflows/{id}` | руководитель, администратор | `WorkflowOut` |
| `POST /api/v1/workflows/{id}/statuses` | руководитель, администратор | 201 `StatusOut` (добавляется в конец) |
| `PATCH /api/v1/workflow-statuses/{id}` | руководитель, администратор | `StatusOut` |
| `PUT /api/v1/workflows/{id}/status-order` | руководитель, администратор | `WorkflowOut` |

```json
// WorkflowOut
{
  "id": 1, "name": "Типовое взаимодействие с вузом", "description": "…", "is_default": true, "is_active": true,
  "statuses": [{"id": 1, "name": "Поиск контакта", "position": 0, "is_final": false, "is_active": true}]
}
```

- `POST /workflows`: `{"name": "…", "description": "…", "statuses": ["Заявка", "Готово"]}` — от 1 до 50 статусов без повторов (иначе 422); последний статус помечается финальным; повтор названия процесса — 409.
- `PATCH /workflows/{id}`: `{"name"?, "description"?, "is_active"?}`; отключить базовый процесс нельзя — 409 (`details[].field = "is_active"`).
- `PATCH /workflow-statuses/{id}`: `{"name"?, "is_final"?, "is_active"?}`. 409 — повтор названия в процессе (`name`), отключение статуса, в котором сейчас есть взаимодействия, или последнего активного статуса (`is_active`). Переименование не меняет историю: записи ссылаются на статус по идентификатору и показывают его текущее название.
- `PUT /workflows/{id}/status-order`: `{"status_ids": [3, 1, 2]}` — все статусы процесса ровно по одному разу, иначе 422 (`status_ids`).

Каждое изменение записывается в журнал действий (`workflow.create`, `workflow.update`, `workflow_status.create`, `workflow_status.update`, `workflow.reorder`).

## Смена статуса

`POST /api/v1/launches/{id}/status-changes` — `multipart/form-data`, все роли в своей области видимости (иначе 404).

| Поле | Обязательно | Правила |
|---|---|---|
| `status_id` | да | активный статус процесса этого взаимодействия |
| `comment` | нет | до 2000 символов, пробелы по краям удаляются |
| `files` | нет | поле повторяется; до 5 файлов по 20 МБ |

Допустимые форматы: png, jpg/jpeg, pdf, zip, gz/gzip, rar, doc, docx, xls, xlsx. Формат проверяется и по расширению, и по содержимому файла. Тот же статус можно указать, только если есть комментарий или файл — так к текущему этапу добавляются заметки.

Ответ 201 — `StatusChangeOut`:

```json
{
  "id": 12, "launch_id": 4,
  "from_status": {"id": 1, "name": "Поиск контакта"},
  "to_status": {"id": 3, "name": "Встреча"},
  "comment": "Встреча назначена",
  "author": {"id": 2, "full_name": "Анна Демо"},
  "created_at": "2026-09-16T01:10:00Z",
  "attachments": [{"id": 5, "filename": "протокол.pdf", "content_type": "application/pdf", "size_bytes": 48211, "created_at": "2026-09-16T01:10:00Z"}]
}
```

Ошибки:

| Код | HTTP | Когда |
|---|---|---|
| `VALIDATION_ERROR` | 422 | статус недоступен (`status_id`), тот же статус без комментария и файлов, комментарий длиннее 2000 (`comment`), больше 5 файлов (`files`) |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | формат не из списка или содержимое не соответствует расширению (`files`) |
| `PAYLOAD_TOO_LARGE` | 413 | файл больше 20 МБ (`files`); запрос больше 105 МБ отклоняет nginx |
| `RECORD_NOT_FOUND` | 404 | взаимодействие не найдено или вне области видимости |

При любой ошибке смена не сохраняется и уже записанные файлы удаляются. В журнал действий попадает событие `launch.status_change` без текста комментария и имён файлов.

`GET /api/v1/launches/{id}/status-changes` — история `StatusChangeOut[]`, новые записи первыми.

Прежние `PATCH /api/v1/launches/{id}` (`{"stage": n}`) и `GET /api/v1/launches/{id}/history` продолжают работать: номер этапа равен позиции статуса в базовом процессе, а смена этапа тоже записывается в историю статусов.

## Файлы

`GET /api/v1/attachments/{id}` — скачивание в области видимости взаимодействия (иначе 404). Ответ отдаётся как вложение (`Content-Disposition: attachment`) с заголовками `X-Content-Type-Options: nosniff` и `Cache-Control: private, no-store`.

Файлы хранятся в томе Docker `attachments_data` под случайными именами; в базе — исходное имя, тип, размер и SHA-256. Резервное копирование тома — `docs/operations/backup.md`.
