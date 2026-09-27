#!/usr/bin/env bash
# Back up and release the public Compose stack in a fixed, checked order.
set -euo pipefail
set +x
umask 077
cd "$(dirname "$0")/.."

config="${DEPLOY_CONFIG_FILE:-deploy/local/public-deploy.env}"
[[ -f "$config" && -r "$config" ]] || {
  echo "deployment config is missing or unreadable: $config" >&2; exit 2;
}
mode="$(stat -f %Lp "$config" 2>/dev/null || stat -c %a "$config")"
if (( (8#$mode & 077) != 0 )); then
  echo 'deployment config must not be accessible to group or others' >&2; exit 2
fi
# The local file is operator-managed and must contain only shell assignments.
source "$config"
: "${BACKUP_DIR:?set BACKUP_DIR in the deployment config}"
: "${DEPLOY_CHECKOUT:?set DEPLOY_CHECKOUT in the deployment config}"
if [[ "$(cd "$DEPLOY_CHECKOUT" && pwd -P)" != "$(pwd -P)" ]]; then
  echo 'deployment config belongs to a different checkout' >&2; exit 2
fi
export BACKUP_DIR BACKUP_AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
export BACKUP_AGE_RECIPIENTS_FILE="${BACKUP_AGE_RECIPIENTS_FILE:-}"
export BACKUP_STATUS_DIR="${BACKUP_STATUS_DIR:-./deploy/local/backup-status}"
export COMPOSE_PROJECT_NAME=edu-crm

command -v docker >/dev/null || { echo 'docker is required' >&2; exit 2; }
command -v curl >/dev/null || { echo 'curl is required' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'python3 is required' >&2; exit 2; }
source scripts/backup-age.sh
backup_age_recipient_preflight
backup_private_directory
docker compose version >/dev/null

label="${1:-deploy-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "$label" =~ ^[a-z0-9-]+$ ]] || { echo 'label must match [a-z0-9-]+' >&2; exit 2; }
attempts="${DEPLOY_HEALTH_ATTEMPTS:-30}"
[[ "$attempts" =~ ^[1-9][0-9]*$ ]] || { echo 'DEPLOY_HEALTH_ATTEMPTS must be positive' >&2; exit 2; }

check_http() {
  local url="$1" attempt
  for (( attempt=1; attempt<=attempts; attempt++ )); do
    if curl --fail --silent --show-error --max-time 8 --output /dev/null "$url" 2>/dev/null; then
      return 0
    fi
    if (( attempt < attempts )); then sleep 2; fi
  done
  echo "health check failed: $url" >&2
  return 1
}

echo 'Creating encrypted database and attachment backups'
dump="$(scripts/db-backup.sh "$label")"
archive="$(scripts/attachments-backup.sh "$label")"
python3 scripts/record-backup-status.py "${BACKUP_STATUS_DIR:-deploy/local/backup-status}/status.json" \
  "$dump" "$archive" "$label"

echo 'Building API, web, and notification images'
docker compose -f compose.yaml -f compose.public.yaml --profile notifications build api web notifier
echo 'Releasing API'
docker compose -f compose.yaml -f compose.public.yaml up -d --no-deps api
check_http 'http://127.0.0.1:8000/api/v1/health'
echo 'Releasing notification scheduler'
docker compose -f compose.yaml -f compose.public.yaml --profile notifications up -d --no-deps notifier
echo 'Releasing web'
docker compose -f compose.yaml -f compose.public.yaml up -d --no-deps web
check_http 'http://127.0.0.1:8080/'
check_http 'https://unicrm.tech/'
check_http 'https://unicrm.tech/api/v1/health'
if [[ "$(docker compose -f compose.yaml -f compose.public.yaml --profile notifications ps --status running --services notifier)" != 'notifier' ]]; then
  echo 'notification scheduler is not running' >&2
  exit 1
fi

# Realm imports do not update an existing realm. Keep branding and custom logins in sync.
echo 'Updating the existing login branding and login mode'
brand="$(docker compose exec -T keycloak bash -s <<'KEYCLOAK'
set -euo pipefail
set +x
: "${KC_BOOTSTRAP_ADMIN_USERNAME:?missing Keycloak admin user}"
: "${KC_BOOTSTRAP_ADMIN_PASSWORD:?missing Keycloak admin password}"
config="$(mktemp)"
chmod 600 "$config"
trap 'rm -f "$config"' EXIT
kcadm=/opt/keycloak/bin/kcadm.sh
"$kcadm" config credentials --server http://localhost:8080/auth --realm master \
  --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" \
  --config "$config" >/dev/null
"$kcadm" update realms/edu-crm -s displayName=UniCRM -s displayNameHtml=UniCRM \
  -s registrationEmailAsUsername=false -s editUsernameAllowed=false \
  --config "$config" >/dev/null
"$kcadm" get realms/edu-crm --fields displayName,displayNameHtml,registrationEmailAsUsername,editUsernameAllowed --config "$config"
KEYCLOAK
)"
if ! printf '%s' "$brand" | python3 -c 'import json, sys; data = json.load(sys.stdin); sys.exit(0 if data.get("displayName") == data.get("displayNameHtml") == "UniCRM" and data.get("registrationEmailAsUsername") is False and data.get("editUsernameAllowed") is False else 1)'; then
  echo 'login branding or mode readback failed' >&2
  exit 1
fi

# curl returns the redirect without following it. Keep OIDC state and cookies out of logs.
login="$(curl --silent --show-error --max-time 8 --output /dev/null \
  --write-out '%{http_code}\n%{redirect_url}' 'https://unicrm.tech/api/v1/auth/login')"
status="${login%%$'\n'*}"
redirect="${login#*$'\n'}"
if [[ "$status" != 302 || "$redirect" != https://unicrm.tech/auth/realms/edu-crm/* ]]; then
  echo 'public login redirect check failed' >&2
  exit 1
fi
echo 'Public release checks passed'
