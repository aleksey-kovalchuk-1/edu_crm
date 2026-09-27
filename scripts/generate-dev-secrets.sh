#!/usr/bin/env bash
# Generates random local-development secrets for Keycloak and the API in deploy/local/ (gitignored).
# Existing files are never overwritten, so running it again keeps current passwords and sessions.
set -euo pipefail
cd "$(dirname "$0")/.."

dir=deploy/local
keycloak_env="$dir/keycloak.env"
api_env="$dir/api.env"

random_text() {
  # Letters and digits only, so values are safe in env files and URLs.
  LC_ALL=C openssl rand -base64 64 | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c "$1"
}

if [[ -f "$keycloak_env" && -f "$api_env" ]]; then
  umask 077
  for name in EDU_CRM_MANAGER_1_PASSWORD EDU_CRM_MANAGER_2_PASSWORD EDU_CRM_IRINA_PASSWORD EDU_CRM_ADMIN_1_PASSWORD EDU_CRM_ADMIN_2_PASSWORD; do
    if ! grep -q "^${name}=" "$keycloak_env"; then
      printf '%s=%s\n' "$name" "$(random_text 20)" >> "$keycloak_env"
      echo "Added $name to $keycloak_env; existing passwords were kept."
    fi
  done
  if ! grep -q '^LEARNER_DATA_ENCRYPTION_KEY=' "$api_env"; then
    umask 077
    learner_key="$(openssl rand -base64 32 | tr '+/' '-_')"
    printf '\nLEARNER_DATA_ENCRYPTION_KEY=%s\n' "$learner_key" >> "$api_env"
    echo "Added a separate learner-data key to $api_env; existing secrets were kept."
  else
    echo "Secrets already exist in $dir; nothing to do."
  fi
  if ! grep -q '^FRAUD_MATCH_KEY=' "$api_env"; then
    fraud_key="$(openssl rand -base64 32 | tr '+/' '-_')"
    printf '\nFRAUD_MATCH_KEY=%s\nFRAUD_MATCH_KEY_VERSION=1\n' "$fraud_key" >> "$api_env"
    echo "Added a separate document-match key to $api_env; coverage remains disabled until backfill."
  fi
  exit 0
fi
if [[ -f "$keycloak_env" || -f "$api_env" ]]; then
  echo "Only one of $keycloak_env and $api_env exists; move it aside and run again so both are generated together." >&2
  exit 1
fi

mkdir -p "$dir"
umask 077
client_secret="$(random_text 40)"
admin_client_secret="$(random_text 40)"
# A Fernet key is URL-safe base64 of 32 random bytes.
session_key="$(openssl rand -base64 32 | tr '+/' '-_')"
learner_key="$(openssl rand -base64 32 | tr '+/' '-_')"
fraud_key="$(openssl rand -base64 32 | tr '+/' '-_')"

cat > "$keycloak_env" <<EOF
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_PASSWORD=$(random_text 24)
KC_DB_PASSWORD=$(random_text 32)
EDU_CRM_CLIENT_SECRET=$client_secret
EDU_CRM_ADMIN_CLIENT_SECRET=$admin_client_secret
EDU_CRM_MANAGER_1_PASSWORD=$(random_text 20)
EDU_CRM_MANAGER_2_PASSWORD=$(random_text 20)
EDU_CRM_IRINA_PASSWORD=$(random_text 20)
EDU_CRM_ADMIN_1_PASSWORD=$(random_text 20)
EDU_CRM_ADMIN_2_PASSWORD=$(random_text 20)
EOF

cat > "$api_env" <<EOF
OIDC_CLIENT_SECRET=$client_secret
KEYCLOAK_ADMIN_CLIENT_SECRET=$admin_client_secret
SESSION_ENCRYPTION_KEY=$session_key
LEARNER_DATA_ENCRYPTION_KEY=$learner_key
FRAUD_MATCH_KEY=$fraud_key
FRAUD_MATCH_KEY_VERSION=1
EOF

echo "Created $keycloak_env and $api_env (local development only; never commit them)."
echo "Demo logins: irina_super_admin (руководитель), admin_1/admin_2 (администраторы), manager_1/manager_2 (менеджеры); passwords are in $keycloak_env."
