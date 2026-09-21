#!/usr/bin/env bash
# Grants the edu-crm-admin service account the least-privilege realm-management permissions the
# CRM's Keycloak Admin integration needs: listing users, assigning/removing realm roles, and
# reading the realm's password policy. Run once after the edu-crm-admin client exists in the
# running realm (deploy/keycloak/realm-edu-crm.json) — safe to re-run (both grants below are
# idempotent: add-roles per role, and re-posting an already-present scope-mapping is a no-op).
#
# Two grants are required, not one. edu-crm-admin has fullScopeAllowed=false (deliberately — it
# must not implicitly receive every realm/client role). Under that setting, a role assigned only
# to the service-account *user* (add-roles) never actually reaches a client_credentials token:
# Keycloak only mints into the token the intersection of the user's roles and the roles explicitly
# present in the *client's own* scope-mappings. Verified by hand while building this script:
# granting only the user-role mapping produced tokens with no realm_access/resource_access claims
# at all, and every admin-API call 403'd, until the scope-mapping step below was added too.
set -euo pipefail
cd "$(dirname "$0")/.."

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password"

service_account_username="service-account-edu-crm-admin"
if ! docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get users -r edu-crm \
    --query "username=$service_account_username" --fields id --format csv --noquotes | grep -q .; then
  echo "edu-crm-admin's service account user not found — is the client in the running realm yet?" >&2
  echo "If the realm was imported before this client was added to realm-edu-crm.json, you need to" >&2
  echo "add it to the live realm first (Keycloak admin console, or re-import into a fresh volume)." >&2
  exit 1
fi

# Step 1: grant the roles to the service-account user itself.
docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh add-roles -r edu-crm \
  --uusername "$service_account_username" --cclientid realm-management \
  --rolename view-users --rolename manage-users --rolename view-realm

# Step 2: also add the same roles to the edu-crm-admin client's own scope-mappings. Required
# because fullScopeAllowed=false restricts which of the user's roles are actually minted into
# tokens this client requests, independent of what the service-account user is assigned above.
admin_client_id=$(docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients -r edu-crm \
  --query clientId=edu-crm-admin --fields id --format csv --noquotes | tail -n1 | tr -d '\r')
realm_management_id=$(docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients -r edu-crm \
  --query clientId=realm-management --fields id --format csv --noquotes | tail -n1 | tr -d '\r')

scope_roles_json="["
first=true
for role_name in view-users manage-users view-realm; do
  role_id=$(docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get \
    "clients/$realm_management_id/roles/$role_name" -r edu-crm --fields id --format csv --noquotes \
    | tail -n1 | tr -d '\r')
  if [ "$first" = true ]; then first=false; else scope_roles_json+=","; fi
  scope_roles_json+="{\"id\":\"$role_id\",\"name\":\"$role_name\"}"
done
scope_roles_json+="]"

echo "$scope_roles_json" | docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh create \
  "clients/$admin_client_id/scope-mappings/clients/$realm_management_id" -r edu-crm -f -

echo "Granted view-users, manage-users, view-realm to $service_account_username (user role mapping + client scope mapping)."
