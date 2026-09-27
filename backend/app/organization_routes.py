"""Настройки → Организация (spec 2026-09-27-organization-settings): everyone signed in reads the card,
crm-admin/crm-superadmin edit it, and the public brand endpoint exposes only the name for the login screen."""
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERADMIN, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import OrganizationProfile, utcnow
from .organization import format_phone, organization_name, validate_ogrn
from .phone import PhoneFormatError, normalize_phone

router = APIRouter(prefix='/api/v1/organization', tags=['Организация'])
any_role = require_roles(*ALL_ROLES)
org_admin = require_roles(ROLE_ADMIN, ROLE_SUPERADMIN)

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
FIELDS = ('name', 'legal_name', 'ogrn', 'registration_date', 'legal_address', 'postal_address',
          'contact_address', 'phone', 'email')


class OrganizationIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Short
    legal_name: Long
    ogrn: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
    registration_date: date
    legal_address: Long
    postal_address: Long
    contact_address: Long
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
    email: EmailStr


class OrganizationOut(BaseModel):
    name: str
    legal_name: str
    ogrn: str
    registration_date: date
    legal_address: str
    postal_address: str
    contact_address: str
    phone: str
    phone_display: str
    email: str
    updated_at: datetime | None


class BrandOut(BaseModel):
    name: str


def _field_error(field, message):
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': field, 'message': message, 'type': 'value_error'}])


def _card(db):
    row = db.get(OrganizationProfile, 1)
    if row is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND, 'Карточка организации не создана')
    return row


def organization_out(row):
    return OrganizationOut(**{f: getattr(row, f) for f in FIELDS}, phone_display=format_phone(row.phone),
                           updated_at=row.updated_at)


@router.get('', response_model=OrganizationOut, summary='Карточка организации', dependencies=[Depends(any_role)])
def get_organization(db: Session = Depends(get_db)):
    return organization_out(_card(db))


@router.put('', response_model=OrganizationOut, summary='Изменить карточку организации')
def update_organization(data: OrganizationIn, request: Request, auth: AuthContext = Depends(org_admin),
                        db: Session = Depends(get_db)):
    if not validate_ogrn(data.ogrn):
        raise _field_error('ogrn', 'ОГРН — 13 цифр с верной контрольной цифрой')
    if data.registration_date > date.today():
        raise _field_error('registration_date', 'Дата регистрации не может быть в будущем')
    try:
        phone = normalize_phone(data.phone)
    except PhoneFormatError:
        raise _field_error('phone', 'Телефон в формате +7 (XXX) XXX-XX-XX')
    row = _card(db)
    values = {**data.model_dump(), 'phone': phone, 'email': str(data.email)}
    changed = [f for f in FIELDS if getattr(row, f) != values[f]]
    for field in changed:
        setattr(row, field, values[field])
    if changed:
        row.updated_at = utcnow()
        row.updated_by_user_id = auth.user.id
        record_event(db, request, auth.user, 'organization.update', entity_type='organization', entity_id=1,
                     summary='Изменена карточка организации', payload={'fields': changed})
    db.commit()
    return organization_out(row)


@router.get('/brand', response_model=BrandOut, summary='Название организации для экрана входа')
def brand(db: Session = Depends(get_db)):
    # Public on purpose: the login screen shows the name before anyone signs in. Name only, nothing else.
    return BrandOut(name=organization_name(db))
