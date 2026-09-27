import os
import base64
import binascii
from dataclasses import dataclass
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

LOCAL_EXAMPLE_URL = 'postgresql+psycopg://crm:local-demo-only@127.0.0.1:5432/edu_crm'
FERNET_KEY_HINT = 'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
REQUIRED_AUTH_SETTINGS = (
    'OIDC_ISSUER',
    'OIDC_INTERNAL_BASE_URL',
    'OIDC_CLIENT_ID',
    'OIDC_CLIENT_SECRET',
    'PUBLIC_BASE_URL',
    'SESSION_ENCRYPTION_KEY',
)


class SettingsError(RuntimeError):
    """Raised at startup when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    oidc_issuer: str
    oidc_internal_base_url: str
    oidc_client_id: str
    oidc_client_secret: str
    public_base_url: str
    session_encryption_key: str
    learner_data_encryption_key: str = ''
    fraud_match_key: str = ''
    fraud_match_key_version: int = 1
    fraud_match_coverage_complete: bool = False
    fraud_batch_row_limit: int = 500
    fraud_hourly_import_limit: int = 10
    session_ttl_hours: int = 8
    session_revalidate_seconds: int = 120
    cookie_secure: bool = True
    allowed_origins: tuple[str, ...] = ()
    attachments_dir: str = '/data/attachments'
    backup_status_file: str = ''
    # SMS provider for CRM-owned phone verification (D-not-yet-numbered; see docs/design/phone-verification.md).
    # Unset in local dev/CI on purpose: app/sms.py falls back to a logging-only sender so the code is
    # visible (API container log) without any real gateway account. Real credentials are supplied only
    # through deploy/local/api.env, never committed.
    sms_provider_url: str = ''
    sms_provider_api_key: str = ''
    sms_sender: str = 'CRM'
    # Keycloak Admin API access (Users & Roles, Security's password-policy display). Unset by
    # default — admin features degrade to "not configured" rather than the app failing to start;
    # see keycloak_admin.py. Real credentials come only from deploy/local/*.env, never committed.
    keycloak_admin_client_id: str = ''
    keycloak_admin_client_secret: str = ''
    keycloak_admin_base_url: str = ''
    # Outgoing email for university correspondence (Настройки → Личный профиль). Unset in local
    # dev/CI on purpose, same as sms_provider_url: app/email.py falls back to a logging-only sender
    # so the code is visible (API container log) without any real provider account. Real credentials
    # are supplied only through deploy/local/api.env, never committed.
    email_provider_url: str = ''
    email_provider_api_key: str = ''
    email_sender_name: str = 'UniCRM'
    email_sender_address: str = ''

    @property
    def callback_url(self):
        return f'{self.public_base_url}/api/v1/auth/callback'

    @property
    def trusted_origins(self):
        return frozenset({self.public_base_url, *self.allowed_origins})


def validate_database_url(url):
    url = (url or '').strip()
    if not url:
        raise SettingsError(f'DATABASE_URL is not set. Example for local development: {LOCAL_EXAMPLE_URL}')
    if not url.startswith('postgresql'):
        raise SettingsError('Only PostgreSQL is supported: DATABASE_URL must start with "postgresql"')
    return url


def normalize_origin(value, name):
    value = value.strip().rstrip('/')
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise SettingsError(f'{name} must be an origin such as http://localhost:8080, got {value!r}')
    return value


def _positive_int(environ, name, default):
    raw = (environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise SettingsError(f'{name} must be a positive integer, got {raw!r}') from error
    if value <= 0:
        raise SettingsError(f'{name} must be a positive integer, got {raw!r}')
    return value


def _boolean(environ, name, default):
    raw = (environ.get(name) or '').strip().lower()
    if not raw:
        return default
    if raw in {'true', '1', 'yes'}:
        return True
    if raw in {'false', '0', 'no'}:
        return False
    raise SettingsError(f'{name} must be true or false, got {raw!r}')


def database_url_from_environment(environ=None):
    """Only the database URL, for tools such as migrations and seeding that do not need login settings."""
    environ = os.environ if environ is None else environ
    return validate_database_url(environ.get('DATABASE_URL'))


def load_settings(environ=None):
    environ = os.environ if environ is None else environ
    database_url = database_url_from_environment(environ)

    missing = [name for name in REQUIRED_AUTH_SETTINGS if not (environ.get(name) or '').strip()]
    if missing:
        raise SettingsError(f'Required settings are not set: {", ".join(missing)}')

    encryption_key = environ['SESSION_ENCRYPTION_KEY'].strip()
    try:
        Fernet(encryption_key)
    except (ValueError, TypeError) as error:
        raise SettingsError(f'SESSION_ENCRYPTION_KEY must be a Fernet key; generate one with: {FERNET_KEY_HINT}') from error

    learner_key = (environ.get('LEARNER_DATA_ENCRYPTION_KEY') or '').strip()
    if learner_key:
        try:
            Fernet(learner_key)
        except (ValueError, TypeError) as error:
            raise SettingsError('LEARNER_DATA_ENCRYPTION_KEY must be a separate Fernet key') from error
        if learner_key == encryption_key:
            raise SettingsError('LEARNER_DATA_ENCRYPTION_KEY must differ from SESSION_ENCRYPTION_KEY')

    fraud_key = (environ.get('FRAUD_MATCH_KEY') or '').strip()
    if fraud_key:
        try:
            decoded = base64.b64decode(fraud_key, altchars=b'-_', validate=True)
        except (ValueError, binascii.Error) as error:
            raise SettingsError('FRAUD_MATCH_KEY must encode 32 random bytes') from error
        if len(decoded) != 32:
            raise SettingsError('FRAUD_MATCH_KEY must encode 32 random bytes')
        other_keys = [encryption_key, learner_key]
        if any(other and decoded == base64.urlsafe_b64decode(other) for other in other_keys):
            raise SettingsError('FRAUD_MATCH_KEY must differ from encryption keys')
    fraud_coverage = _boolean(environ, 'FRAUD_MATCH_COVERAGE_COMPLETE', False)
    if fraud_coverage and not fraud_key:
        raise SettingsError('FRAUD_MATCH_COVERAGE_COMPLETE requires FRAUD_MATCH_KEY')

    allowed_origins = tuple(
        normalize_origin(origin, 'ALLOWED_ORIGINS')
        for origin in (environ.get('ALLOWED_ORIGINS') or '').split(',')
        if origin.strip()
    )
    return Settings(
        database_url=database_url,
        oidc_issuer=environ['OIDC_ISSUER'].strip().rstrip('/'),
        oidc_internal_base_url=environ['OIDC_INTERNAL_BASE_URL'].strip().rstrip('/'),
        oidc_client_id=environ['OIDC_CLIENT_ID'].strip(),
        oidc_client_secret=environ['OIDC_CLIENT_SECRET'].strip(),
        public_base_url=normalize_origin(environ['PUBLIC_BASE_URL'], 'PUBLIC_BASE_URL'),
        session_encryption_key=encryption_key,
        learner_data_encryption_key=learner_key,
        fraud_match_key=fraud_key,
        fraud_match_key_version=_positive_int(environ, 'FRAUD_MATCH_KEY_VERSION', 1),
        fraud_match_coverage_complete=fraud_coverage,
        fraud_batch_row_limit=_positive_int(environ, 'FRAUD_BATCH_ROW_LIMIT', 500),
        fraud_hourly_import_limit=_positive_int(environ, 'FRAUD_HOURLY_IMPORT_LIMIT', 10),
        session_ttl_hours=_positive_int(environ, 'SESSION_TTL_HOURS', 8),
        session_revalidate_seconds=_positive_int(environ, 'SESSION_REVALIDATE_SECONDS', 120),
        cookie_secure=_boolean(environ, 'COOKIE_SECURE', True),
        allowed_origins=allowed_origins,
        attachments_dir=(environ.get('ATTACHMENTS_DIR') or '').strip() or '/data/attachments',
        backup_status_file=(environ.get('BACKUP_STATUS_FILE') or '').strip(),
        sms_provider_url=(environ.get('SMS_PROVIDER_URL') or '').strip(),
        sms_provider_api_key=(environ.get('SMS_PROVIDER_API_KEY') or '').strip(),
        sms_sender=(environ.get('SMS_SENDER') or '').strip() or 'CRM',
        keycloak_admin_client_id=(environ.get('KEYCLOAK_ADMIN_CLIENT_ID') or '').strip(),
        keycloak_admin_client_secret=(environ.get('KEYCLOAK_ADMIN_CLIENT_SECRET') or '').strip(),
        keycloak_admin_base_url=environ['OIDC_INTERNAL_BASE_URL'].strip().rstrip('/').rsplit('/realms/', 1)[0],
        email_provider_url=(environ.get('EMAIL_PROVIDER_URL') or '').strip(),
        email_provider_api_key=(environ.get('EMAIL_PROVIDER_API_KEY') or '').strip(),
        email_sender_name=(environ.get('EMAIL_SENDER_NAME') or '').strip() or 'UniCRM',
        email_sender_address=(environ.get('EMAIL_SENDER_ADDRESS') or '').strip(),
    )
