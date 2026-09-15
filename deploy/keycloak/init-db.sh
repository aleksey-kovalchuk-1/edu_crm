#!/bin/sh
# Creates Keycloak's own role and database on the shared PostgreSQL server.
# Idempotent: runs on every `docker compose up` and only changes what is missing; the password is kept in sync.
set -eu
: "${KC_DB_PASSWORD:?KC_DB_PASSWORD is required (run scripts/generate-dev-secrets.sh)}"

psql -v ON_ERROR_STOP=1 -v kc_password="$KC_DB_PASSWORD" <<'SQL'
select 'create role keycloak login' where not exists (select from pg_roles where rolname = 'keycloak')\gexec
alter role keycloak with login password :'kc_password';
select 'create database keycloak owner keycloak' where not exists (select from pg_database where datname = 'keycloak')\gexec
SQL
echo "Keycloak database is ready"
