# Apache Superset (опционально)

Встроенный экран аналитики React уже получает демонстрационную статистику через FastAPI. Superset подключается отдельно к агрегированной витрине PostgreSQL. Встраивание дашборда в React не реализовано.

Контейнерный профиль подготовлен, но не проверен запуском в текущей среде: Docker отсутствует. Образ закреплён для воспроизводимости; перед внешним развёртыванием обновить его до согласованного и проверенного релиза.

1. Запустить основной стек по README. Сгенерировать непустой `SUPERSET_SECRET_KEY` и записать в `.env`.
2. Выполнить:

```bash
docker compose --profile analytics up -d --build
docker compose exec superset superset db upgrade
docker compose exec superset superset fab create-admin
docker compose exec superset superset init
docker compose exec -T db psql -U crm -d edu_crm < superset/readonly.sql
```

`create-admin` интерактивно запрашивает учётные данные. SQL создаёт BI-роль один раз. Пароль `local-analytics-only` предназначен только для локального демо.

3. Открыть http://localhost:8088 и добавить PostgreSQL-подключение:

```text
postgresql+psycopg2://analytics_reader:local-analytics-only@db:5432/edu_crm
```

4. Добавить dataset `public.analytics_annual`: временной срез `year`, метрики SUM(applications), SUM(students), SUM(streams). Создать столбчатую диаграмму и таблицу.

BI-роль не получает доступ к контактам, карточкам и задачам. Для промышленного подключения заменить пароли и метаданные SQLite Superset на поддерживаемую производственную БД, настроить SSO, резервирование и сетевой доступ.
