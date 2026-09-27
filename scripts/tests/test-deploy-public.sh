#!/usr/bin/env bash
# Exercises release ordering with synthetic backups and fake Docker/HTTP commands.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -m 700 "$tmp/bin" "$tmp/backups" "$tmp/attachments"
printf 'synthetic attachment\n' > "$tmp/attachments/member.txt"
age-keygen -o "$tmp/identity" >/dev/null 2>&1
recipient="$(age-keygen -y "$tmp/identity")"
printf 'BACKUP_DIR=%q\nBACKUP_AGE_RECIPIENT=%q\nDEPLOY_CHECKOUT=%q\n' \
  "$tmp/backups" "$recipient" "$root" > "$tmp/deploy.env"
chmod 600 "$tmp/deploy.env"

cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_DOCKER_LOG"
case "$*" in
  'compose version') : ;;
  *'exec -T db pg_dump '*) printf 'synthetic database\n' ;;
  *'exec -T api tar -C /data/attachments -czf - .'*)
    if [[ "${FAIL_ATTACHMENT:-}" == 1 ]]; then exit 7; fi
    tar -C "$FAKE_ATTACHMENTS" -czf - . ;;
  *'build api web notifier') : ;;
  *'up -d --no-deps api') : ;;
  *'up -d --no-deps notifier') : ;;
  *'up -d --no-deps web') : ;;
  *'ps --status running --services notifier') printf 'notifier\n' ;;
  'compose exec -T keycloak bash -s')
    if [[ "${FAIL_BRAND_UPDATE:-}" == 1 ]]; then exit 7; fi
    if [[ "${BAD_BRAND_READBACK:-}" == 1 ]]; then
      printf '{"displayName":"Образование CRM","displayNameHtml":"Образование CRM"}\n'
    elif [[ "${BAD_LOGIN_MODE:-}" == 1 ]]; then
      printf '{"displayName":"UniCRM","displayNameHtml":"UniCRM","registrationEmailAsUsername":true,"editUsernameAllowed":false}\n'
    else
      printf '{"displayName":"UniCRM","displayNameHtml":"UniCRM","registrationEmailAsUsername":false,"editUsernameAllowed":false}\n'
    fi ;;
  *) echo "unexpected Docker command: $*" >&2; exit 9 ;;
esac
EOF
cat > "$tmp/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
url="${*: -1}"
printf '%s\n' "$url" >> "$FAKE_CURL_LOG"
if [[ "$url" == 'https://unicrm.tech/api/v1/auth/login' ]]; then
  if [[ "${BAD_REDIRECT:-}" == 1 ]]; then
    printf '302\nhttps://elsewhere.example/auth/realms/edu-crm/\n'
  else
    printf '302\nhttps://unicrm.tech/auth/realms/edu-crm/protocol/openid-connect/auth\n'
  fi
  exit 0
fi
if [[ "$url" == 'http://127.0.0.1:8000/api/v1/health' && "${FAIL_API_HEALTH:-}" == 1 ]]; then exit 22; fi
exit 0
EOF
chmod +x "$tmp/bin/docker" "$tmp/bin/curl"
export PATH="$tmp/bin:$PATH" FAKE_DOCKER_LOG="$tmp/docker.log" FAKE_CURL_LOG="$tmp/curl.log"
export FAKE_ATTACHMENTS="$tmp/attachments" DEPLOY_CONFIG_FILE="$tmp/deploy.env" DEPLOY_HEALTH_ATTEMPTS=1
export BACKUP_STATUS_DIR="$tmp/status"

"$root/scripts/deploy-public.sh" synthetic-success >/dev/null
dump="$(find "$tmp/backups" -name '*.dump.age' -print -quit)"
archive="$(find "$tmp/backups" -name '*.tar.gz.age' -print -quit)"
test -n "$dump" && test -n "$archive"
test "$(age -d -i "$tmp/identity" "$dump")" = 'synthetic database'
test "$(age -d -i "$tmp/identity" "$archive" | tar -tzf - | rg -c 'member.txt')" = 1
test -z "$(find "$tmp/backups" -name '*.dump' -o -name '*.tar.gz' -o -name '*.partial*')"
python3 - "$tmp/status/status.json" <<'PY'
import json, sys
entry = json.load(open(sys.argv[1]))['backups'][0]
assert entry['source'] == 'synthetic-success' and entry['database_bytes'] > 0
assert entry['attachments_bytes'] > 0 and entry['verified'] is False
PY
python3 - "$tmp/docker.log" <<'PY'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text().splitlines()
markers = ('pg_dump', 'tar -C /data/attachments', 'build api web notifier', 'up -d --no-deps api', 'up -d --no-deps notifier', 'up -d --no-deps web', 'exec -T keycloak bash -s')
positions = [next(i for i, line in enumerate(lines) if marker in line) for marker in markers]
assert positions == sorted(positions), lines
PY
rg -q '^https://unicrm.tech/api/v1/auth/login$' "$tmp/curl.log"

: > "$tmp/docker.log"
if FAIL_ATTACHMENT=1 "$root/scripts/deploy-public.sh" synthetic-attachment-fail >/dev/null 2>&1; then
  echo 'deployment continued after attachment backup failed' >&2; exit 1
fi
! rg -q 'build api web|up -d --no-deps' "$tmp/docker.log"

: > "$tmp/docker.log"
if FAIL_API_HEALTH=1 "$root/scripts/deploy-public.sh" synthetic-api-fail >/dev/null 2>&1; then
  echo 'deployment continued after API health failed' >&2; exit 1
fi
! rg -q 'up -d --no-deps web' "$tmp/docker.log"

if BAD_REDIRECT=1 "$root/scripts/deploy-public.sh" synthetic-redirect-fail >/dev/null 2>&1; then
  echo 'deployment accepted an external login redirect' >&2; exit 1
fi

if FAIL_BRAND_UPDATE=1 "$root/scripts/deploy-public.sh" synthetic-brand-update-fail >/dev/null 2>&1; then
  echo 'deployment ignored failed Keycloak branding update' >&2; exit 1
fi
if BAD_BRAND_READBACK=1 "$root/scripts/deploy-public.sh" synthetic-brand-readback-fail >/dev/null 2>&1; then
  echo 'deployment accepted stale Keycloak branding' >&2; exit 1
fi
if BAD_LOGIN_MODE=1 "$root/scripts/deploy-public.sh" synthetic-login-mode-fail >/dev/null 2>&1; then
  echo 'deployment accepted a realm that replaces logins with email addresses' >&2; exit 1
fi

printf 'BACKUP_DIR=%q\nBACKUP_AGE_RECIPIENT=%q\nDEPLOY_CHECKOUT=%q\n' \
  "$tmp/backups" "$recipient" "$tmp" > "$tmp/wrong-checkout.env"
chmod 600 "$tmp/wrong-checkout.env"
: > "$tmp/docker.log"
if DEPLOY_CONFIG_FILE="$tmp/wrong-checkout.env" "$root/scripts/deploy-public.sh" synthetic-wrong-checkout >/dev/null 2>&1; then
  echo 'deployment accepted a config for another checkout' >&2; exit 1
fi
test ! -s "$tmp/docker.log"
echo 'Public deployment synthetic checks passed.'
