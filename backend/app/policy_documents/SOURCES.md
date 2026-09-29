# Policy documents (demo versions)

Downloaded 29 Sep 2026 from the owner's publicly shared Google documents through their `.docx` export
(`/export?format=docx`), unchanged. They are demo documents: the CRM labels them «Демонстрационная версия
документа» and they are not legally approved final policies, even where the text says «Утверждено». Served only to
signed-in CRM users by `GET /api/v1/documents/{slug}` (`app/policy_routes.py`); the checksums below are checked
by `tests/test_policy_documents.py`, so a replaced file is noticed.

| File | Section in «Настройки → Персональные данные» | Source | Size | SHA-256 |
|---|---|---|---|---|
| `personal-data-policy.docx` | Политика в области обработки персональных данных | https://docs.google.com/document/d/1J7Ep_4uTl1rbWkkdkP-wncOVe3Cd4G3J/edit (title «Политика UniCRM в отношении обработки персональных данных», edited 28 Sep 2026) | 26404 bytes | `e51f2b5683c3216dd13724747e2a962b8c9490463a6c4342f43c19c5566c9f9d` |
| `information-security-policy.docx` | Политика информационной безопасности | https://docs.google.com/document/d/1aqQQovaxQ2FYPy7k61TEjUAbeIMwsZU-/edit (title «Политика информационной безопасности в организации», edited 28 Sep 2026) | 47120 bytes | `6c71eb58dcbff7a3ca9fdbecc498798bef03d66cca5d06b57ba38beeab293175` |

To update a document: export the new version to `.docx`, replace the file, update its size and checksum here and
in `app/policy_routes.py`, and note the change in `docs/decisions.md`.
