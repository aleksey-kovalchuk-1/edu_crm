"""Injectable SMS sending for CRM-owned phone verification (D-162, D-163).

No real SMS gateway is integrated in this environment (no credentials or provider API spec were
available — see docs/decisions.md D-163). `send_sms` picks one of two concrete implementations
based on `settings.sms_provider_url`:

- Unset (the default in local dev/CI): a logging-only sender. The phone and message are written
  to the API container's log at INFO level and the call returns as if the SMS had been sent —
  analogous to how Mailpit lets local dev "see" outgoing email without a real mail server.
- Set: a generic, best-effort HTTP POST to `sms_provider_url`:
    POST {sms_provider_url}
    Authorization: Bearer {sms_provider_api_key}
    Content-Type: application/json
    {"to": "<phone>", "from": "<sms_sender>", "text": "<message>"}
  Any non-2xx response (or a network failure) raises SmsSendError so the caller fails closed.

  IMPORTANT for whoever wires up a real gateway later: this request/response shape is NOT a real
  provider's documented API. It was invented as a plausible generic contract because the actual
  gateway (presumably Rostelecom-operated, per D-163) was not available to integrate against or
  test with in this environment. Before pointing `SMS_PROVIDER_URL` at a real gateway in a
  non-local environment, replace the body of `_http_sender` with a call that matches that
  provider's real request fields, auth scheme, and success/error response shape.

The `sender` parameter on `send_sms` (defaulting to the module's own settings-based choice) is
what makes this injectable: `app/main.py` stores the chosen callable on `app.state.sms_sender`
(defaulting to `send_sms` itself), and tests substitute a fake there to assert what would have
been sent without performing real HTTP calls or asserting on log output.
"""
import logging

import httpx

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0


class SmsSendError(RuntimeError):
    """Raised when an SMS could not be sent; the caller is expected to fail closed on this."""


def _log_sender(settings, phone, message):
    logger.info('SMS to %s: %s', phone, message)


def _http_sender(settings, phone, message):
    try:
        response = httpx.post(
            settings.sms_provider_url,
            json={'to': phone, 'from': settings.sms_sender, 'text': message},
            headers={'Authorization': f'Bearer {settings.sms_provider_api_key}'},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SmsSendError(f'SMS provider request failed: {error}') from error


def send_sms(settings, phone, message) -> None:
    """Sends `message` to `phone`; raises SmsSendError on failure. See module docstring for the contract."""
    sender = _http_sender if settings.sms_provider_url else _log_sender
    sender(settings, phone, message)
