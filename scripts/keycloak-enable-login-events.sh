#!/usr/bin/env bash
# Enables Keycloak login-event storage for the edu-crm realm (30-day retention) and lets the CRM's
# service account read it (view-events), for Настройки → Безопасность → «История входов».
# Idempotent: re-setting the realm fields and re-adding an existing role/scope-mapping change nothing.
# Events are recorded only from the moment this runs. Run against the live realm only at release,
# with the owner's approval (spec docs/superpowers/specs/2026-09-27-security-settings-design.md).
set -euo pipefail
cd "$(dirname "$0")/.."

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)
kcadm() { docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh "$@"; }

kcadm config credentials --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password" >/dev/null

# Event listeners are left exactly as configured on the live realm (storage is independent of them).
kcadm update realms/edu-crm \
  -s eventsEnabled=true \
  -s eventsExpiration=2592000 \
  -s 'enabledEventTypes=["LOGIN","LOGIN_ERROR","LOGOUT","UPDATE_PASSWORD"]'

service_account_username="service-account-edu-crm-admin"
kcadm add-roles -r edu-crm --uusername "$service_account_username" --cclientid realm-management --rolename view-events

# fullScopeAllowed=false on edu-crm-admin: the role must also be in the client's scope-mappings to reach its tokens.
admin_client_id=$(kcadm get clients -r edu-crm --query clientId=edu-crm-admin --fields id --format csv --noquotes | tail -n1 | tr -d '\r')
realm_management_id=$(kcadm get clients -r edu-crm --query clientId=realm-management --fields id --format csv --noquotes | tail -n1 | tr -d '\r')
role_id=$(kcadm get "clients/$realm_management_id/roles/view-events" -r edu-crm --fields id --format csv --noquotes | tail -n1 | tr -d '\r')
echo "[{\"id\":\"$role_id\",\"name\":\"view-events\"}]" | \
  kcadm create "clients/$admin_client_id/scope-mappings/clients/$realm_management_id" -r edu-crm -f -

echo "Login events are now stored for 30 days and readable by the CRM service account."
