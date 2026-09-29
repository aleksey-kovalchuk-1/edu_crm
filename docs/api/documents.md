# API документов (политики)

Решение D-242. Файлы и их происхождение — `backend/app/policy_documents/SOURCES.md`.

- `GET /api/v1/documents/personal-data-policy` — демонстрационная версия «Политики в области обработки персональных
  данных» (`UniCRM_Политика_обработки_персональных_данных_демо.docx`).
- `GET /api/v1/documents/information-security-policy` — демонстрационная версия «Политики информационной
  безопасности» (`UniCRM_Политика_информационной_безопасности_демо.docx`).

Любая роль CRM. Ответ `200`: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
`Content-Disposition: attachment` с именем файла (UTF-8, `filename*`), `Cache-Control: private, no-store`.
Без входа — `401 UNAUTHENTICATED`; неизвестный документ — `404`. Интерфейс: «Настройки → Персональные данные».
