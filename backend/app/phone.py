"""Russian phone number normalization for CRM-owned phone verification (D-161-D-163).

Kept separate from `profile_routes.py` so the format rules are independently testable, and
referenced from `models.py`'s `PhoneVerificationCode` docstring.
"""
import re

PHONE_FORMAT_MESSAGE = (
    'Введите номер телефона в формате +7XXXXXXXXXX, 8XXXXXXXXXX или 7XXXXXXXXXX '
    '(10 цифр после кода страны)'
)


class PhoneFormatError(ValueError):
    """The given text is not one of the accepted Russian phone number formats."""


# The only characters allowed alongside digits: common formatting separators. A leading '+' is
# handled separately below (it is not valid anywhere else in the string).
_ALLOWED_SEPARATORS = ' -()'
_STRICT_FORMAT = re.compile(r'^[78]\d{10}$')


def normalize_phone(raw: str) -> str:
    """Normalizes +7XXXXXXXXXX / 8XXXXXXXXXX / 7XXXXXXXXXX (only spaces, hyphens and parentheses as
    formatting) to +7XXXXXXXXXX.

    Strict on purpose: this only strips a documented whitelist of formatting characters, not every
    non-digit character in the input. Free text that merely *contains* 11 digits (a sentence, a
    pasted address, someone else's number embedded in a note) must be rejected, not silently
    accepted by extracting the digits from it.

    Raises PhoneFormatError (with a Russian message) for anything else.
    """
    text = (raw or '').strip()
    body = text[1:] if text.startswith('+') else text
    if not body or '+' in body:
        raise PhoneFormatError(PHONE_FORMAT_MESSAGE)
    cleaned = ''.join(ch for ch in body if ch not in _ALLOWED_SEPARATORS)
    if not _STRICT_FORMAT.match(cleaned):
        raise PhoneFormatError(PHONE_FORMAT_MESSAGE)
    return f'+7{cleaned[1:]}'


def mask_phone(phone: str) -> str:
    """+7•••••••XX: enough to recognize a number in an audit trail, not enough to read it."""
    return f'+7{"•" * 8}{phone[-2:]}'
