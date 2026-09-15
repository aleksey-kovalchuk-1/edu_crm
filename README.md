# Образование CRM

Первый рабочий шаблон управления взаимодействиями с учебными заведениями. Ориентиры по сценариям — CRM B2B, IQHR, ЛКО РТК ИТ: единое окно, связанные карточки, этапы, ответственные и аналитика. Это самостоятельная реализация, без исходного кода и фирменных ресурсов РТК ИТ.

## Что работает

- Обзор с показателями и распределением программ по этапам.
- Реестр учебных заведений: создание, поиск, переход к программам.
- Доска взаимодействий: создание программы, поиск, фильтр просрочки.
- Карточка программы: продукт, ответственный, число обучающихся, срок, смена этапа и история.
- Завершение и повторное открытие демонстрационных задач.
- Годовая аналитика и выгрузка CSV.
- FastAPI с OpenAPI; SQLAlchemy и PostgreSQL через Docker Compose.
- Опциональная конфигурация Superset и роль для чтения агрегированной статистики.

Все учреждения, люди и показатели в демо вымышлены. `students` — одно демонстрационное число по запуску, без индивидуального учёта студентов. Исторические показатели 2023–2025 независимы от текущих карточек. При заполнении БД даты задач формируются относительно даты первого запуска.

## Запуск через Docker

Нужны Docker Engine, Docker Compose v2 и `openssl` (для генерации локальных секретов).

```bash
cp .env.example .env
scripts/generate-dev-secrets.sh
docker compose up --build -d
```

Вход выполняется через Keycloak: при открытии CRM браузер переходит на страницу входа. Первый запуск Keycloak занимает около минуты. Демонстрационные учётные записи: `anna.demo` (менеджер), `pavel.demo` (руководитель), `irina.demo` (администратор). Пароли создаются случайными и лежат в `deploy/local/keycloak.env` — этот файл не попадает в git. Консоль администратора Keycloak: http://localhost:8080/auth/admin (пользователь `admin`, пароль в том же файле).

- CRM: http://localhost:8080
- API Swagger: http://localhost:8080/api/docs (схема OpenAPI: http://localhost:8080/api/openapi.json)
- Проверка API: http://localhost:8080/api/v1/health
- Коды ошибок API: [docs/api/errors.md](docs/api/errors.md)

Данные PostgreSQL сохраняются в volume `postgres_data`. `docker compose down` сохраняет этот volume. Для пустой БД установите `SEED_DEMO=false` до первого запуска. Демоданные добавляются один раз при старте контейнера `api` (`python -m app.seed`) и не дублируются при перезапуске. API запускается в нескольких процессах (`WEB_CONCURRENCY`, по умолчанию 4).

Пароль в `.env` используется в URL БД: для демо оставьте пример; при замене используйте URL-безопасное значение либо задайте корректно закодированный DATABASE_URL в Compose.

## Локальная разработка без Docker

Python 3.12 и Node.js 22. Поддерживается только PostgreSQL; переменная `DATABASE_URL` обязательна — без неё API не запустится. База из Compose доступна на `127.0.0.1:5432`.

```bash
docker compose up -d db
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt -c backend/constraints.txt
cd backend
DATABASE_URL=postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/edu_crm SEED_DEMO=true \
  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

В другом терминале:

```bash
cd frontend
npm ci
npm run dev
```

Открыть http://localhost:5173. Vite перенаправляет `/api` на порт 8000.

## Проверки

Тесты работают только с PostgreSQL: для каждого теста создаётся отдельная база из шаблона и удаляется после теста. По умолчанию используется сервер из Compose (`127.0.0.1:5432`); другой сервер задаётся через `TEST_DATABASE_URL` (URL служебной базы `postgres`). Рабочая база `edu_crm` тестами не затрагивается.

```bash
docker compose up -d db
cd backend
../.venv/bin/python -m pytest -q
cd ../frontend
npm run build
```

Результаты проверок по задачам фиксируются в `docs/night-report.md`.

## Структура

```text
backend/app/       модели, схемы, FastAPI, демоданные
backend/tests/     интеграционные тесты API
frontend/src/      React, типизированный API-клиент, стили
superset/         опциональный BI-контейнер и SQL витрины
docs/             план и инструкция Superset
.github/workflows/ CI: API-тесты и frontend build
```

## Границы шаблона

Это локальный прототип. Вход — через Keycloak с ролями «Менеджер», «Руководитель» и «Администратор»; каждая точка API проверяет роль и CSRF-токен для изменений ([устройство входа](docs/design/authentication.md)). Порты Compose привязаны к `127.0.0.1`. Ещё не реализованы: ограничение данных по закреплённым вузам, журнал действий пользователей, документы и подписание, настоящие LMS/API заказчика, импорт статистики и прогнозирование. Соответствие 152-ФЗ и приказу ФСТЭК № 117 не заявляется. До загрузки реальных персональных данных нужны журнал действий и ограничение доступа к данным. Этапы пока меняются свободно; регламент переходов будет задан по материалам заказчика.

Схема базы управляется миграциями Alembic (`backend/migrations`). Контейнер `api` применяет их при каждом старте (`python -m app.db_migrate`); база, созданная до появления миграций, помечается базовой ревизией без пересоздания и потери данных. Локально без Docker: `cd backend && DATABASE_URL=... python -m app.db_migrate`. Перед миграциями делайте резервную копию ([инструкция](docs/operations/backup.md)). Запускать один API-процесс при первоначальном заполнении.

[Подключение Superset](docs/superset.md)

## Репозиторий GitHub

https://github.com/aleksey-kovalchuk-1/edu_crm

```bash
git clone https://github.com/aleksey-kovalchuk-1/edu_crm.git
cd edu_crm
cp .env.example .env
scripts/generate-dev-secrets.sh
docker compose up --build -d
```

Основная ветка: `main`. Проверки API и сборки интерфейса описаны в `.github/workflows/ci.yml`.
