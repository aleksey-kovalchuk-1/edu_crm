"""Protected learner profiles. List/search never serialize document identifiers."""
import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import _email, like_pattern, not_found
from .db import get_db
from .errors import AppError, ErrorCode
from .models import Learner

router = APIRouter(prefix='/api/v1/learners', tags=['Слушатели'])
viewer = require_roles(*ALL_ROLES)
full_access = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]

SENSITIVE = {
    'snils': 'snils_encrypted',
    'passport_series': 'passport_series_encrypted',
    'passport_number': 'passport_number_encrypted',
    'passport_issued_by': 'passport_issued_by_encrypted',
    'passport_department_code': 'passport_department_code_encrypted',
    'diploma_number': 'diploma_number_encrypted',
    'diploma_series': 'diploma_series_encrypted',
    'diploma_registration_number': 'diploma_registration_number_encrypted',
}
PLAIN_FIELDS = (
    'last_name', 'first_name', 'middle_name', 'phone', 'email', 'passport_issued_at',
    'gender', 'birth_date', 'registration_region', 'registration_locality',
    'registration_street', 'registration_house', 'registration_apartment', 'postal_code',
    'dative_first_name', 'dative_last_name', 'dative_middle_name', 'education',
    'diploma_profession', 'diploma_institution', 'diploma_last_name', 'diploma_issued_at',
)


class LearnerPatch(BaseModel):
    last_name: Name | None = None
    first_name: Name | None = None
    middle_name: Text200 | None = None
    phone: Phone | None = None
    email: Email | None = None
    snils: Identifier | None = None
    passport_series: Identifier | None = None
    passport_number: Identifier | None = None
    passport_issued_by: Text300 | None = None
    passport_issued_at: date | None = None
    passport_department_code: Identifier | None = None
    gender: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    birth_date: date | None = None
    registration_region: Text200 | None = None
    registration_locality: Text200 | None = None
    registration_street: Text200 | None = None
    registration_house: Identifier | None = None
    registration_apartment: Identifier | None = None
    postal_code: Identifier | None = None
    dative_first_name: Text200 | None = None
    dative_last_name: Text200 | None = None
    dative_middle_name: Text200 | None = None
    education: Text200 | None = None
    diploma_profession: Text200 | None = None
    diploma_institution: Text200 | None = None
    diploma_last_name: Text200 | None = None
    diploma_number: Identifier | None = None
    diploma_series: Identifier | None = None
    diploma_registration_number: Identifier | None = None
    diploma_issued_at: date | None = None

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        return None if value is None else _email(value)

    @field_validator('snils', 'passport_series', 'passport_number', 'passport_department_code', 'postal_code')
    @classmethod
    def valid_identifier(cls, value, info):
        if value is None or value == '':
            return value
        patterns = {
            'snils': r'[0-9 -]{11,14}',
            'passport_series': r'\d{4}',
            'passport_number': r'\d{6}',
            'passport_department_code': r'\d{3}-?\d{3}',
            'postal_code': r'\d{6}',
        }
        digits = re.sub(r'\D', '', value)
        lengths = {'snils': 11, 'passport_series': 4, 'passport_number': 6,
                   'passport_department_code': 6, 'postal_code': 6}
        if not re.fullmatch(patterns[info.field_name], value) or len(digits) != lengths[info.field_name]:
            raise ValueError('Неверный формат идентификатора')
        return value


class LearnerIn(LearnerPatch):
    last_name: Name
    first_name: Name
    middle_name: Text200 = ''
    phone: Phone = ''
    email: Email = ''


class LearnerSummary(BaseModel):
    id: int
    last_name: str
    first_name: str
    middle_name: str
    phone: str
    email: str


class LearnerOut(LearnerPatch):
    id: int
    last_name: str
    first_name: str
    middle_name: str
    phone: str
    email: str


def summary(record):
    return LearnerSummary(id=record.id, last_name=record.last_name, first_name=record.first_name,
                          middle_name=record.middle_name, phone=record.phone, email=record.email)


def full(record, request):
    values = {'id': record.id, **{field: getattr(record, field) for field in PLAIN_FIELDS}}
    cipher = request.app.state.learner_cipher
    if cipher is None and any(getattr(record, column) for column in SENSITIVE.values()):
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Ключ анкеты слушателя не настроен')
    for field, column in SENSITIVE.items():
        stored = getattr(record, column)
        if stored:
            decrypted = cipher.decrypt(stored)
            if decrypted is None:
                raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Не удалось прочитать защищённую анкету')
            values[field] = decrypted
        else:
            values[field] = None
    return LearnerOut.model_validate(values)


def apply_fields(record, submitted, request):
    cipher = request.app.state.learner_cipher
    if any(submitted.get(field) for field in SENSITIVE) and cipher is None:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE, 'Ключ анкеты слушателя не настроен')
    for field, value in submitted.items():
        if field in SENSITIVE:
            setattr(record, SENSITIVE[field], cipher.encrypt(value) if value else None)
        else:
            setattr(record, field, value)


@router.get('', response_model=list[LearnerSummary])
def list_learners(q: str | None = None, auth: AuthContext = Depends(viewer), db: Session = Depends(get_db)):
    query = select(Learner).order_by(Learner.last_name, Learner.first_name, Learner.id)
    if q:
        pattern = like_pattern(q)
        query = query.where(or_(
            Learner.last_name.ilike(pattern, escape='\\'), Learner.first_name.ilike(pattern, escape='\\'),
            Learner.middle_name.ilike(pattern, escape='\\'), Learner.phone.ilike(pattern, escape='\\'),
            Learner.email.ilike(pattern, escape='\\'),
        ))
    return [summary(record) for record in db.scalars(query.limit(100)).all()]


@router.get('/{learner_id}', response_model=LearnerOut)
def get_learner(learner_id: int, request: Request, auth: AuthContext = Depends(full_access), db: Session = Depends(get_db)):
    record = db.get(Learner, learner_id)
    if record is None:
        raise not_found()
    return full(record, request)


@router.post('', response_model=LearnerOut, status_code=201)
def create_learner(data: LearnerIn, request: Request, auth: AuthContext = Depends(full_access), db: Session = Depends(get_db)):
    record = Learner(last_name=data.last_name, first_name=data.first_name)
    apply_fields(record, data.model_dump(exclude_none=True), request)
    db.add(record)
    db.flush()
    record_event(db, request, auth.user, 'learner.create', entity_type='learner', entity_id=record.id,
                 summary='Создана анкета слушателя', payload={})
    db.commit()
    return full(record, request)


@router.patch('/{learner_id}', response_model=LearnerOut)
def update_learner(learner_id: int, data: LearnerPatch, request: Request,
                   auth: AuthContext = Depends(full_access), db: Session = Depends(get_db)):
    record = db.get(Learner, learner_id)
    if record is None:
        raise not_found()
    submitted = data.model_dump(exclude_unset=True)
    if submitted:
        apply_fields(record, submitted, request)
        record_event(db, request, auth.user, 'learner.update', entity_type='learner', entity_id=record.id,
                     summary='Изменена анкета слушателя', payload={'fields': sorted(submitted)})
        db.commit()
    return full(record, request)
