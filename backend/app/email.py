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
    {"to": "<address>", "from": "<from_address or email_sender_address>", "from_name": "<from_name or email_sender_name>",
     "subject": "<subject>", "text": "<body>"}
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
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0


class EmailSendError(RuntimeError):
    """Raised when an email could not be sent; the caller is expected to fail closed on this."""


def _log_sender(settings, to, subject, body, *, from_address=None, from_name=None):
    logger.info('Email to %s from %s <%s>: %s\n%s', to, from_name or settings.email_sender_name,
                from_address or settings.email_sender_address, subject, body)


def _http_sender(settings, to, subject, body, *, from_address=None, from_name=None):
    try:
        response = httpx.post(
            settings.email_provider_url,
            json={'to': to, 'from': from_address or settings.email_sender_address,
                  'from_name': from_name or settings.email_sender_name, 'subject': subject, 'text': body},
            headers={'Authorization': f'Bearer {settings.email_provider_api_key}'},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise EmailSendError(f'Email provider request failed: {error}') from error


def _smtp_sender(settings, to, subject, body, *, from_address=None, from_name=None):
    message = EmailMessage()
    message['From'] = formataddr((from_name or settings.email_sender_name, from_address or settings.email_sender_address))
    message['To'] = to
    message['Subject'] = subject
    message.set_content(body)
    try:
        if settings.email_smtp_port == 465:
            connection = smtplib.SMTP_SSL(settings.email_smtp_host, settings.email_smtp_port,
                                          timeout=REQUEST_TIMEOUT_SECONDS, context=ssl.create_default_context())
        else:
            connection = smtplib.SMTP(settings.email_smtp_host, settings.email_smtp_port, timeout=REQUEST_TIMEOUT_SECONDS)
        with connection as smtp:
            if settings.email_smtp_port != 465:
                smtp.starttls(context=ssl.create_default_context())
            if settings.email_smtp_user:
                smtp.login(settings.email_smtp_user, settings.email_smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise EmailSendError(f'SMTP delivery failed: {error}') from error


def email_configured(settings) -> bool:
    """Whether a real provider is set up; the log-only fallback never counts as delivery."""
    return bool(settings.email_smtp_host or settings.email_provider_url)


def send_email(settings, to, subject, body, *, from_address: str | None = None, from_name: str | None = None) -> None:
    """Sends an email to `to`; raises EmailSendError on failure. See module docstring for the contract.
    A Russian SMTP mailbox (EMAIL_SMTP_HOST) wins over the generic HTTP provider."""
    if settings.email_smtp_host:
        sender = _smtp_sender
    else:
        sender = _http_sender if settings.email_provider_url else _log_sender
    sender(settings, to, subject, body, from_address=from_address, from_name=from_name)
