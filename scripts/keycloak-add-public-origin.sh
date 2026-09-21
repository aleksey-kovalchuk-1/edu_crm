#!/usr/bin/env bash
# Idempotently adds a public origin to the edu-crm-api Keycloak client's redirect URIs / web
# origins / post-logout redirect URIs, alongside the existing localhost ones (never removes them,
# so local dev keeps working). Needed because Keycloak's --import-realm only imports a realm that
# does not yet exist; an already-running realm must be updated live via kcadm.
set -euo pipefail
cd "$(dirname "$0")/.."

public_origin="${1:?Usage: scripts/keycloak-add-public-origin.sh https://unicrm.tech}"

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password"

client_uuid=$(docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh get clients \
  -r edu-crm --query clientId=edu-crm-api --fields id --format csv --noquotes | tail -n1 | tr -d '\r')

docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh update "clients/$client_uuid" -r edu-crm \
  --set "redirectUris=[\"http://localhost:8080/api/v1/auth/callback\",\"http://localhost:5173/api/v1/auth/callback\",\"$public_origin/api/v1/auth/callback\"]" \
  --set "webOrigins=[\"http://localhost:8080\",\"http://localhost:5173\",\"$public_origin\"]" \
  --set "attributes.\"post.logout.redirect.uris\"=http://localhost:8080/*##http://localhost:5173/*##$public_origin/*"

echo "Added $public_origin to the edu-crm-api client's redirect/web origins (localhost entries kept)."
