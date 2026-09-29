#!/usr/bin/env bash
# Points Keycloak's own e-mails (confirming the address after sign-up, «Забыли пароль») at the same Russian SMTP
# mailbox the API uses (owner decision 2026-09-28: Russian providers only). Reads EMAIL_SMTP_HOST, EMAIL_SMTP_PORT,
# EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_SENDER_ADDRESS and EMAIL_SENDER_NAME from deploy/local/api.env, so
# the mailbox is configured in one place. Refuses a server or sender outside .ru. Never prints the password.
# Preview by default; --apply changes Keycloak and reads the settings back. Idempotent.
# Rollback: kcadm update realms/edu-crm -s 'smtpServer={}' (Keycloak then sends nothing, as before). Note: kcadm's
# --fields filter returns nested objects empty, so the settings are read from the whole realm.
set -euo pipefail
cd "$(dirname "$0")/.."

apply=false
[ "${1:-}" = "--apply" ] && apply=true

value() { grep "^$1=" deploy/local/api.env | head -1 | cut -d= -f2- || true; }
host=$(value EMAIL_SMTP_HOST | tr 'A-Z' 'a-z')
port=$(value EMAIL_SMTP_PORT); port=${port:-465}
user=$(value EMAIL_SMTP_USER)
from=$(value EMAIL_SENDER_ADDRESS)
name=$(value EMAIL_SENDER_NAME); name=${name:-UniCRM}

ru() { [[ "$1" =~ ^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+ru$ ]]; }
[ -n "$host" ] || { echo "STOP: EMAIL_SMTP_HOST is not set in deploy/local/api.env (e.g. smtp.yandex.ru)."; exit 1; }
ru "$host" || { echo "STOP: $host is not a Russian (.ru) mail server."; exit 1; }
ru "$(printf '%s' "${from#*@}" | tr 'A-Z' 'a-z')" || { echo "STOP: EMAIL_SENDER_ADDRESS must be in a .ru domain."; exit 1; }
[[ "$port" =~ ^[0-9]+$ ]] || { echo "STOP: EMAIL_SMTP_PORT must be a number."; exit 1; }

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)
kcadm() { docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh "$@"; }
kcadm config credentials --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password" >/dev/null

summary() { python3 -c '
import json, sys
s = json.load(sys.stdin).get("smtpServer") or {}
print(" ".join(k + "=" + str(s.get(k, "")) for k in ("host", "port", "from", "ssl", "starttls", "auth")))'; }

current=$(kcadm get realms/edu-crm | summary)
ssl=false; starttls=true
[ "$port" = 465 ] && { ssl=true; starttls=false; }
wanted="host=$host port=$port from=$from ssl=$ssl starttls=$starttls auth=$([ -n "$user" ] && echo true || echo false)"
echo "Keycloak mail now: $current"
echo "Wanted:            $wanted"
if [ "$current" = "$wanted" ]; then echo "Already up to date."; exit 0; fi
$apply || { echo "Preview only; run with --apply to change Keycloak."; exit 0; }

HOST="$host" PORT="$port" FROM="$from" NAME="$name" USER_NAME="$user" SSL="$ssl" STARTTLS="$starttls" \
PASSWORD="$(value EMAIL_SMTP_PASSWORD)" python3 -c '
import json, os
e = os.environ
smtp = {"host": e["HOST"], "port": e["PORT"], "from": e["FROM"], "fromDisplayName": e["NAME"],
        "ssl": e["SSL"], "starttls": e["STARTTLS"], "auth": "true" if e["USER_NAME"] else "false"}
if e["USER_NAME"]:
    smtp.update(user=e["USER_NAME"], password=e["PASSWORD"])
print(json.dumps({"smtpServer": smtp}))' | kcadm update realms/edu-crm -f -

after=$(kcadm get realms/edu-crm | summary)
echo "Keycloak mail now: $after"
[ "$after" = "$wanted" ] || { echo "STOP: read-back does not match"; exit 1; }
echo "Done. Check it: «Забыли пароль» on the sign-in page for your own .ru address."
