"""The organization card (spec 2026-09-27-organization-settings): validation helpers and the one place
every screen, export and email reads the organization name from."""
import re

from .models import OrganizationProfile

OGRN_RE = re.compile(r'^\d{13}$')
FALLBACK_NAME = 'UniCRM'


def validate_ogrn(value: str) -> bool:
    """13 digits; the last one is (first 12 digits mod 11) mod 10."""
    if not OGRN_RE.match(value or ''):
        return False
    return int(value[:12]) % 11 % 10 == int(value[12])


def format_phone(value: str) -> str:
    """'+74951966205' → '+7 (495) 196-62-05'; anything else is returned unchanged."""
    if not re.fullmatch(r'\+7\d{10}', value or ''):
        return value or ''
    d = value[2:]
    return f'+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}'


def organization_name(db) -> str:
    row = db.get(OrganizationProfile, 1)
    return row.name if row is not None else FALLBACK_NAME
