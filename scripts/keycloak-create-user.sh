#!/usr/bin/env bash
# Creates or updates a Keycloak test user through the Admin REST API: administrative mechanism for T-080-ish
# test accounts (alongside assigning roles by hand in the Keycloak admin console). Idempotent: safe to re-run.
#
# Usage: scripts/keycloak-create-user.sh <username> <email> <role[,role...]>
#   role is one or more of: crm-user, crm-supervisor, crm-admin (comma-separated for more than one)
#
# Every run sets emailVerified=true, enabled=true, a freshly generated password (printed once, never stored),
# and exactly the requested realm roles (any of the three CRM roles the user already had are removed if not
# requested again, so re-running the script always leaves the account matching what you asked for).
#
# Requires deploy/local/keycloak.env (scripts/generate-dev-secrets.sh) and the dev stack reachable at
# KEYCLOAK_BASE_URL (default: http://localhost:8080/auth, i.e. through nginx, matching D-122).
set -euo pipefail
cd "$(dirname "$0")/.."

REALM=edu-crm
KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://localhost:8080/auth}"
KNOWN_ROLES="crm-user crm-supervisor crm-admin"

username="${1:-}"
email="${2:-}"
roles_csv="${3:-}"

if [[ -z "$username" || -z "$email" || -z "$roles_csv" ]]; then
  echo "Usage: $0 <username> <email> <role[,role...]>" >&2
  echo "role is one or more of: crm-user, crm-supervisor, crm-admin" >&2
  exit 2
fi
if [[ "$email" != *.ru && "$email" != *.RU ]]; then
  echo "Warning: $email is not a .ru address; self-registration would reject it, but an admin-created account is not checked against that rule." >&2
fi

IFS=',' read -r -a roles <<< "$roles_csv"
for role in "${roles[@]}"; do
  if [[ ! " $KNOWN_ROLES " == *" $role "* ]]; then
    echo "Unknown role '$role'; must be one of: $KNOWN_ROLES" >&2
    exit 2
  fi
done

env_file="deploy/local/keycloak.env"
if [[ ! -f "$env_file" ]]; then
  echo "$env_file not found; run scripts/generate-dev-secrets.sh first." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
: "${KC_BOOTSTRAP_ADMIN_USERNAME:?KC_BOOTSTRAP_ADMIN_USERNAME missing from $env_file}"
: "${KC_BOOTSTRAP_ADMIN_PASSWORD:?KC_BOOTSTRAP_ADMIN_PASSWORD missing from $env_file}"

random_password() {
  LC_ALL=C openssl rand -base64 64 | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 20
}

admin_token() {
  curl -sf -X POST "$KEYCLOAK_BASE_URL/realms/master/protocol/openid-connect/token" \
    -d "client_id=admin-cli" -d "grant_type=password" \
    -d "username=$KC_BOOTSTRAP_ADMIN_USERNAME" -d "password=$KC_BOOTSTRAP_ADMIN_PASSWORD" \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

api() {
  # api METHOD PATH [JSON_BODY]
  local method="$1" path="$2" body="${3:-}"
  local args=(-sf -X "$method" "$KEYCLOAK_BASE_URL/admin/realms/$REALM$path" -H "Authorization: Bearer $TOKEN")
  if [[ -n "$body" ]]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi
  curl "${args[@]}"
}

TOKEN="$(admin_token)"
password="$(random_password)"

user_id="$(api GET "/users?username=$username&exact=true" | python3 -c "
import sys, json
users = json.load(sys.stdin)
print(users[0]['id'] if users else '')
")"

user_json=$(python3 -c "
import json
print(json.dumps({
    'username': '$username',
    'email': '$email',
    'emailVerified': True,
    'enabled': True,
}))
")

if [[ -z "$user_id" ]]; then
  api POST "/users" "$user_json" > /dev/null
  user_id="$(api GET "/users?username=$username&exact=true" | python3 -c "import sys, json; print(json.load(sys.stdin)[0]['id'])")"
  echo "Created user $username ($user_id)"
else
  api PUT "/users/$user_id" "$user_json" > /dev/null
  echo "Updated user $username ($user_id)"
fi

credential_json=$(python3 -c "
import json
print(json.dumps({'type': 'password', 'value': '''$password''', 'temporary': False}))
")
api PUT "/users/$user_id/reset-password" "$credential_json" > /dev/null

# Reconcile realm role mappings: exactly the requested CRM roles, none of the other two.
current_crm_roles="$(api GET "/users/$user_id/role-mappings/realm" | python3 -c "
import sys, json
known = {'crm-user', 'crm-supervisor', 'crm-admin'}
mine = [r['name'] for r in json.load(sys.stdin) if r['name'] in known]
print(' '.join(mine))
")"

to_add=()
for role in "${roles[@]}"; do
  if [[ ! " $current_crm_roles " == *" $role "* ]]; then
    to_add+=("$role")
  fi
done
to_remove=()
for role in $current_crm_roles; do
  if [[ ! " ${roles[*]} " == *" $role "* ]]; then
    to_remove+=("$role")
  fi
done

role_rep() {
  api GET "/roles/$1"
}

if [[ ${#to_add[@]} -gt 0 ]]; then
  reps="["
  for role in "${to_add[@]}"; do
    reps+="$(role_rep "$role"),"
  done
  reps="${reps%,}]"
  api POST "/users/$user_id/role-mappings/realm" "$reps" > /dev/null
fi
if [[ ${#to_remove[@]} -gt 0 ]]; then
  reps="["
  for role in "${to_remove[@]}"; do
    reps+="$(role_rep "$role"),"
  done
  reps="${reps%,}]"
  curl -sf -X DELETE "$KEYCLOAK_BASE_URL/admin/realms/$REALM/users/$user_id/role-mappings/realm" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$reps" > /dev/null
fi

echo "Roles: ${roles[*]}"
echo "Password (shown once): $password"
