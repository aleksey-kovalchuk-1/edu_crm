#!/usr/bin/env bash
# Generates random local-development secrets for Keycloak and the API in deploy/local/ (gitignored).
# Existing files are never overwritten, so running it again keeps current passwords and sessions.
set -euo pipefail
cd "$(dirname "$0")/.."

dir=deploy/local
keycloak_env="$dir/keycloak.env"
api_env="$dir/api.env"

if [[ -f "$keycloak_env" && -f "$api_env" ]]; then
  echo "Secrets already exist in $dir; nothing to do."
  exit 0
fi
if [[ -f "$keycloak_env" || -f "$api_env" ]]; then
  echo "Only one of $keycloak_env and $api_env exists; move it aside and run again so both are generated together." >&2
  exit 1
fi

random_text() {
  # Letters and digits only, so values are safe in env files and URLs.
  LC_ALL=C openssl rand -base64 64 | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c "$1"
}

mkdir -p "$dir"
umask 077
client_secret="$(random_text 40)"
# A Fernet key is URL-safe base64 of 32 random bytes.
session_key="$(openssl rand -base64 32 | tr '+/' '-_')"

cat > "$keycloak_env" <<EOF
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_PASSWORD=$(random_text 24)
KC_DB_PASSWORD=$(random_text 32)
EDU_CRM_CLIENT_SECRET=$client_secret
EDU_CRM_DEMO_USER_PASSWORD=$(random_text 20)
EDU_CRM_DEMO_SUPERVISOR_PASSWORD=$(random_text 20)
EDU_CRM_DEMO_ADMIN_PASSWORD=$(random_text 20)
# Google's own published "always pass" test key pair (D-158); see deploy/local/keycloak.env.example
# for how to swap in real reCAPTCHA keys before any non-local deployment.
RECAPTCHA_SITE_KEY=6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI
RECAPTCHA_SECRET_KEY=6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe
EOF

cat > "$api_env" <<EOF
OIDC_CLIENT_SECRET=$client_secret
SESSION_ENCRYPTION_KEY=$session_key
CONNECTOR_API_KEY=$(random_text 40)
EOF

echo "Created $keycloak_env and $api_env (local development only; never commit them)."
echo "Demo logins: anna.demo (менеджер), pavel.demo (руководитель), irina.demo (администратор); passwords are in $keycloak_env."
