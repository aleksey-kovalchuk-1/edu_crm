#!/usr/bin/env bash
# Brings an existing realm's sign-in pages in line with the repository (realm imports never update an existing
# realm): the UniCRM login theme (deploy/keycloak/themes/edu-crm) and the .ru rule on the e-mail field with the
# sentence people see, instead of a message key that shows up raw when no theme defines it.
# Preview by default; --apply changes Keycloak and reads both settings back. Idempotent.
# Rollback: kcadm update realms/edu-crm -s loginTheme=keycloak.v2 (the rule's message change is harmless).
set -euo pipefail
cd "$(dirname "$0")/.."

apply=false
[ "${1:-}" = "--apply" ] && apply=true

THEME=edu-crm
PATTERN='^[^@\s]+@[^@\s]+\.[rR][uU]$'
MESSAGE='Укажите адрес электронной почты в домене .ru, например ivanov@mail.ru.'

admin_user=$(grep '^KC_BOOTSTRAP_ADMIN_USERNAME=' deploy/local/keycloak.env | cut -d= -f2)
admin_password=$(grep '^KC_BOOTSTRAP_ADMIN_PASSWORD=' deploy/local/keycloak.env | cut -d= -f2)
kcadm() { docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh "$@"; }

kcadm config credentials --server http://localhost:8080/auth --realm master \
  --user "$admin_user" --password "$admin_password" >/dev/null

if ! docker compose exec -T keycloak test -f "/opt/keycloak/themes/$THEME/login/theme.properties"; then
  echo "STOP: the $THEME theme is not mounted in the keycloak container (compose.yaml volume); nothing changed."
  exit 1
fi

theme=$(kcadm get realms/edu-crm --fields loginTheme --format csv --noquotes | tr -d '\r')
echo "loginTheme: ${theme:-(default)}"
[ "$theme" = "$THEME" ] || echo "Would set loginTheme to $THEME"

profile=$(kcadm get users/profile -r edu-crm)
wanted=$(PATTERN="$PATTERN" MESSAGE="$MESSAGE" python3 -c '
import json, os, sys
profile = json.load(sys.stdin)
email = next(a for a in profile["attributes"] if a["name"] == "email")
rule = {"pattern": os.environ["PATTERN"], "error-message": os.environ["MESSAGE"]}
current = email.setdefault("validations", {}).get("pattern")
print("e-mail rule now: " + json.dumps(current, ensure_ascii=False), file=sys.stderr)
if current == rule:
    sys.exit(0)
email["validations"]["pattern"] = rule
print(json.dumps(profile, ensure_ascii=False))
' <<<"$profile")
[ -n "$wanted" ] && echo "Would set the e-mail rule to: .ru only, message «${MESSAGE}»"

if [ "$theme" = "$THEME" ] && [ -z "$wanted" ]; then echo "Already up to date."; exit 0; fi
$apply || { echo "Preview only; run with --apply to change Keycloak."; exit 0; }

[ "$theme" = "$THEME" ] || kcadm update realms/edu-crm -s "loginTheme=$THEME"
[ -z "$wanted" ] || kcadm update users/profile -r edu-crm -f - <<<"$wanted"

after_theme=$(kcadm get realms/edu-crm --fields loginTheme --format csv --noquotes | tr -d '\r')
after_rule=$(kcadm get users/profile -r edu-crm | python3 -c '
import json, sys
email = next(a for a in json.load(sys.stdin)["attributes"] if a["name"] == "email")
print(json.dumps(email.get("validations", {}).get("pattern"), ensure_ascii=False))')
echo "loginTheme now: $after_theme"
echo "e-mail rule now: $after_rule"
if [ "$after_theme" != "$THEME" ] || ! printf '%s' "$after_rule" | grep -qF "$MESSAGE"; then
  echo "STOP: read-back does not match"; exit 1
fi
echo "Done."
