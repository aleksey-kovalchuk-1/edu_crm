#!/usr/bin/env bash
# Idempotently declares the "middleName" (Отчество) attribute in the edu-crm realm's declarative user
# profile. Only admins may edit it inside Keycloak (the CRM writes it with its service account), so
# the Keycloak account console never shows a second name form. Re-running changes nothing.
# Keycloak's --import-realm only imports a realm that does not exist yet, so a running realm is
# updated live via kcadm, like scripts/keycloak-add-public-origin.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)
kcadm() { docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh "$@"; }

kcadm config credentials --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password" >/dev/null

current=$(kcadm get users/profile -r edu-crm)
updated=$(printf '%s' "$current" | python3 scripts/lib/add_middle_name_attribute.py)
if [ "$updated" = "unchanged" ]; then
  echo "middleName is already declared in the edu-crm user profile; nothing to do."
  exit 0
fi
printf '%s' "$updated" | kcadm update users/profile -r edu-crm -f -
echo "Declared middleName (Отчество) in the edu-crm user profile."
