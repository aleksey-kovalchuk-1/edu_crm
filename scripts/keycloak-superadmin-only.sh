#!/usr/bin/env bash
# Makes crm-superadmin carry crm-admin and crm-supervisor (a composite realm role), then removes those two
# roles where they are also assigned directly to a superadmin, so a superadmin holds exactly one CRM role.
# The token's realm-role mapper lists effective (composite-expanded) roles, so permissions do not change.
# Preview by default; --apply changes Keycloak. Idempotent. Stops before removing anything unless the
# inherited roles are already effective, and checks them again afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."

apply=false
[ "${1:-}" = "--apply" ] && apply=true

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)
kcadm() { docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh "$@"; }
names() { tr -d '\r' | sort | tr '\n' ' '; }
has() { case " $1 " in *" $2 "*) return 0 ;; esac; return 1; }

kcadm config credentials --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password" >/dev/null

inherited=$(kcadm get roles/crm-superadmin/composites/realm -r edu-crm --fields name --format csv --noquotes | names)
echo "crm-superadmin includes: ${inherited:-(nothing)}"
missing=()
for role in crm-admin crm-supervisor; do
  has "$inherited" "$role" || missing+=("$role")
done

superadmins=$(kcadm get roles/crm-superadmin/users -r edu-crm --fields id,username --format csv --noquotes | tr -d '\r')
if [ -z "$superadmins" ]; then echo "No user holds crm-superadmin; nothing to do."; exit 0; fi

if [ ${#missing[@]} -gt 0 ]; then
  echo "Would add to crm-superadmin: ${missing[*]}"
  if $apply; then
    args=(); for role in "${missing[@]}"; do args+=(--rolename "$role"); done
    kcadm add-roles -r edu-crm --rname crm-superadmin "${args[@]}"
    echo "Added: ${missing[*]}"
  fi
fi

status=0
while IFS=, read -r id username; do
  [ -n "$id" ] || continue
  direct=$(kcadm get "users/$id/role-mappings/realm" -r edu-crm --fields name --format csv --noquotes | names)
  echo "$username direct roles: $direct"
  redundant=()
  for role in crm-admin crm-supervisor; do
    has "$direct" "$role" && redundant+=("$role")
  done
  if [ ${#redundant[@]} -eq 0 ]; then echo "$username: no redundant direct roles."; continue; fi
  echo "Would remove from $username (inherited through crm-superadmin): ${redundant[*]}"
  $apply || continue
  effective=$(kcadm get "users/$id/role-mappings/realm/composite" -r edu-crm --fields name --format csv --noquotes | names)
  if ! { has "$effective" crm-admin && has "$effective" crm-supervisor; }; then
    echo "STOP: $username would lose inherited roles (effective: $effective)"; status=1; continue
  fi
  for role in "${redundant[@]}"; do kcadm remove-roles -r edu-crm --uid "$id" --rolename "$role"; done
  after_direct=$(kcadm get "users/$id/role-mappings/realm" -r edu-crm --fields name --format csv --noquotes | names)
  after_effective=$(kcadm get "users/$id/role-mappings/realm/composite" -r edu-crm --fields name --format csv --noquotes | names)
  echo "$username direct now: $after_direct"
  echo "$username effective now: $after_effective"
  if ! { has "$after_effective" crm-superadmin && has "$after_effective" crm-admin && has "$after_effective" crm-supervisor; }; then
    echo "STOP: $username effective roles are incomplete after the change"; status=1
  fi
done <<< "$superadmins"
$apply || echo "Preview only. Re-run with --apply to change Keycloak."
exit $status
