"""Injectable email sending for outgoing university correspondence (Настройки → Личный профиль).

No real email provider is integrated in this environment (no credentials or provider API spec
were available). `send_email` picks one of two concrete implementations based on
`settings.email_provider_url`:

- Unset (the default in local dev/CI): a logging-only sender. The recipient, subject and body are
  written to the API container's log at INFO level and the call returns as if the email had been
  sent — same transparency as app/sms.py's own logging-only fallback.
- Set: a generic, best-effort HTTP POST to `email_provider_url`:
    POST {email_provider_url}
    Authorization: Bearer {email_provider_api_key}
    Content-Type: application/json
    {"to": "<address>", "from": "<email_sender_address>", "subject": "<subject>", "text": "<body>"}
  Any non-2xx response (or a network failure) raises EmailSendError so the caller fails closed.

  IMPORTANT for whoever wires up a real provider later: this request/response shape is NOT a real
  provider's documented API — it was invented as a plausible generic contract, exactly like
  app/sms.py's own disclaimer. Replace the body of `_http_sender` with a call matching the real
  provider's request fields, auth scheme, and success/error response shape before pointing
  EMAIL_PROVIDER_URL at anything real.

The `sender` parameter (defaulting to the module's own settings-based choice) is what makes this
injectable: app/main.py stores the chosen callable on app.state.email_sender (defaulting to
send_email itself), and tests substitute a fake there — same pattern as app.state.sms_sender.
"""
import logging

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0


class EmailSendError(RuntimeError):
    """Raised when an email could not be sent; the caller is expected to fail closed on this."""


def _log_sender(settings, to, subject, body):
    logger.info('Email to %s: %s\n%s', to, subject, body)


def _http_sender(settings, to, subject, body):
    try:
        response = httpx.post(
            settings.email_provider_url,
            json={'to': to, 'from': settings.email_sender_address, 'subject': subject, 'text': body},
            headers={'Authorization': f'Bearer {settings.email_provider_api_key}'},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise EmailSendError(f'Email provider request failed: {error}') from error


def send_email(settings, to, subject, body) -> None:
    """Sends an email to `to`; raises EmailSendError on failure. See module docstring for the contract."""
    sender = _http_sender if settings.email_provider_url else _log_sender
    sender(settings, to, subject, body)
