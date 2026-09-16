"""Russian phone number normalization for CRM-owned phone verification (D-155-D-157).

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


def normalize_phone(raw: str) -> str:
    """Normalizes +7XXXXXXXXXX / 8XXXXXXXXXX / 7XXXXXXXXXX (formatting characters allowed) to +7XXXXXXXXXX.

    Raises PhoneFormatError (with a Russian message) for anything else.
    """
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 11 and digits[0] in ('7', '8'):
        subscriber = digits[1:]
    else:
        subscriber = None
    if subscriber is None:
        raise PhoneFormatError(PHONE_FORMAT_MESSAGE)
    return f'+7{subscriber}'


def mask_phone(phone: str) -> str:
    """+7•••••••XX: enough to recognize a number in an audit trail, not enough to read it."""
    return f'+7{"•" * 8}{phone[-2:]}'
