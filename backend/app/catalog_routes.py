"""Catalog and contract API (contract: docs/api/catalogs.md; model: docs/design/catalogs.md).

Managers (crm-user) only see universities they are assigned to and everything attached to them (D-141);
records outside that scope answer 404 so their existence is not revealed.
"""
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import exists, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .db import get_db
from .errors import AppError, ErrorCode
from .models import (
    TRANSFER_STATUSES,
    Contract,
    ITDirection,
    ITProduct,
    University,
    UniversityContact,
    UniversityManager,
    User,
    it_product_directions,
)

router = APIRouter(prefix='/api/v1', tags=['Справочники и договоры'])

any_role = require_roles(*ALL_ROLES)
catalog_editor = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
SEE_ALL_ROLES = frozenset({ROLE_SUPERVISOR, ROLE_ADMIN})

TRANSFER_STATUS_LABELS = {
    'not_started': 'Не начата',
    'in_progress': 'Идёт передача',
    'transferred': 'Передано',
    'cancelled': 'Отменено',
}
EXPIRES_SOON_DAYS = 30

# Constraint name -> (form field, message), so conflicts can be shown next to the right input.
CONFLICT_FIELDS = {
    'universities_name_key': ('name', 'Учебное заведение с таким названием уже есть'),
    'it_directions_name_key': ('name', 'Такое направление уже есть'),
    'it_products_vendor_key': ('name', 'Продукт с таким вендором и названием уже есть'),
    'contracts_contract_number_key': ('contract_number', 'Договор с таким номером уже есть'),
    'university_contacts_university_id_key': ('full_name', 'Контакт с таким ФИО у этого вуза уже есть'),
    'university_managers_pkey': ('user_ids', 'Список ответственных только что изменил другой пользователь; обновите страницу'),
}

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


# ---------- helpers ----------

def sees_all(user):
    return not SEE_ALL_ROLES.isdisjoint(user.roles)


def managed_university_ids(user):
    return select(UniversityManager.university_id).where(UniversityManager.user_id == user.id)


def university_scope(column, user):
    return true() if sees_all(user) else column.in_(managed_university_ids(user))


def one_year_after(day):
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        # 29 February has no counterpart next year.
        return day.replace(year=day.year + 1, day=28)


def like_pattern(text):
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def _raise_conflict(error):
    constraint = getattr(getattr(error.orig, 'diag', None), 'constraint_name', None)
    if constraint in CONFLICT_FIELDS:
        field, message = CONFLICT_FIELDS[constraint]
        raise AppError(ErrorCode.CONFLICT, message, [{'field': field, 'message': message}]) from error
    raise error


def commit_or_conflict(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        _raise_conflict(error)


def flush_or_conflict(db):
    # Creation flushes first so a duplicate is reported before the audit event joins the same transaction.
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        _raise_conflict(error)


def differing(record, changes):
    """Only fields whose value really changes; unchanged submissions must not create audit events."""
    return {field: value for field, value in changes.items() if getattr(record, field) != value}


def not_found():
    return AppError(ErrorCode.RECORD_NOT_FOUND)


def validation_error(field, message):
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': field, 'message': message, 'type': 'value_error'}])


def university_in_scope(db, user, university_id):
    university = db.get(University, university_id)
    if university is None or not (sees_all(user) or db.scalar(select(exists().where(
        UniversityManager.university_id == university_id, UniversityManager.user_id == user.id,
    )))):
        raise not_found()
    return university


def active_university_in_scope(db, user, university_id):
    university = university_in_scope(db, user, university_id)
    if not university.is_active:
        raise validation_error('university_id', 'Учебное заведение неактивно')
    return university


# ---------- IT directions ----------

class DirectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    is_active: bool


class DirectionIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: LongText = ''


class DirectionPatch(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    description: LongText | None = None
    is_active: bool | None = None


@router.get('/it-directions', response_model=list[DirectionOut], summary='ИТ-направления', dependencies=[Depends(any_role)])
def list_directions(q: str | None = None, include_inactive: bool = False, db: Session = Depends(get_db)):
    query = select(ITDirection).order_by(ITDirection.name)
    if not include_inactive:
        query = query.where(ITDirection.is_active.is_(True))
    if q:
        query = query.where(ITDirection.name.ilike(like_pattern(q), escape='\\'))
    return db.scalars(query).all()


@router.post('/it-directions', response_model=DirectionOut, status_code=201, summary='Добавить ИТ-направление')
def create_direction(data: DirectionIn, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    direction = ITDirection(name=data.name, description=data.description)
    db.add(direction)
    flush_or_conflict(db)
    record_event(db, request, auth.user, 'it_direction.create', entity_type='it_direction', entity_id=direction.id,
                 summary=f'Добавлено ИТ-направление «{direction.name}»', payload=data.model_dump())
    db.commit()
    return direction


@router.patch('/it-directions/{direction_id}', response_model=DirectionOut, summary='Изменить ИТ-направление')
def update_direction(direction_id: int, data: DirectionPatch, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    direction = db.get(ITDirection, direction_id)
    if direction is None:
        raise not_found()
    changes = differing(direction, data.model_dump(exclude_unset=True, exclude_none=True))
    if changes:
        for field, value in changes.items():
            setattr(direction, field, value)
        record_event(db, request, auth.user, 'it_direction.update', entity_type='it_direction', entity_id=direction_id,
                     summary=f'Изменено ИТ-направление «{direction.name}»', payload=changes)
        commit_or_conflict(db)
    return direction


# ---------- IT products ----------

class RefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vendor: str
    name: str
    description: str
    is_active: bool
    directions: list[RefOut]


class ProductIn(BaseModel):
    vendor: Name
    name: Name
    description: LongText = ''
    direction_ids: list[int] = Field(default_factory=list, max_length=50)


class ProductPatch(BaseModel):
    vendor: Name | None = None
    name: Name | None = None
    description: LongText | None = None
    direction_ids: list[int] | None = Field(default=None, max_length=50)
    is_active: bool | None = None


def load_directions(db, direction_ids):
    unique_ids = set(direction_ids)
    directions = db.scalars(select(ITDirection).where(ITDirection.id.in_(unique_ids))).all() if unique_ids else []
    if len(directions) != len(unique_ids):
        raise validation_error('direction_ids', 'Указано несуществующее ИТ-направление')
    return sorted(directions, key=lambda direction: direction.name)


def product_out(db, product_id):
    return db.scalar(select(ITProduct).options(selectinload(ITProduct.directions)).where(ITProduct.id == product_id))


@router.get('/it-products', response_model=list[ProductOut], summary='ИТ-продукты', dependencies=[Depends(any_role)])
def list_products(q: str | None = None, direction_id: int | None = None, include_inactive: bool = False, db: Session = Depends(get_db)):
    query = select(ITProduct).options(selectinload(ITProduct.directions)).order_by(ITProduct.vendor, ITProduct.name)
    if not include_inactive:
        query = query.where(ITProduct.is_active.is_(True))
    if q:
        pattern = like_pattern(q)
        query = query.where(or_(ITProduct.name.ilike(pattern, escape='\\'), ITProduct.vendor.ilike(pattern, escape='\\')))
    if direction_id is not None:
        query = query.where(exists().where(
            it_product_directions.c.it_product_id == ITProduct.id, it_product_directions.c.it_direction_id == direction_id,
        ))
    return db.scalars(query).all()


@router.post('/it-products', response_model=ProductOut, status_code=201, summary='Добавить ИТ-продукт')
def create_product(data: ProductIn, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    product = ITProduct(vendor=data.vendor, name=data.name, description=data.description, directions=load_directions(db, data.direction_ids))
    db.add(product)
    flush_or_conflict(db)
    record_event(db, request, auth.user, 'it_product.create', entity_type='it_product', entity_id=product.id,
                 summary=f'Добавлен ИТ-продукт «{product.vendor} — {product.name}»', payload=data.model_dump())
    db.commit()
    return product_out(db, product.id)


@router.patch('/it-products/{product_id}', response_model=ProductOut, summary='Изменить ИТ-продукт')
def update_product(product_id: int, data: ProductPatch, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    product = product_out(db, product_id)
    if product is None:
        raise not_found()
    submitted = data.model_dump(exclude_unset=True, exclude_none=True)
    direction_ids = submitted.pop('direction_ids', None)
    # Look up directions before touching the product: the query would otherwise autoflush a renamed product
    # and surface a duplicate name as an unhandled database error instead of 409.
    directions = load_directions(db, direction_ids) if direction_ids is not None else None
    changes = differing(product, submitted)
    if directions is not None and {d.id for d in directions} != {d.id for d in product.directions}:
        changes['direction_ids'] = sorted(d.id for d in directions)
    if changes:
        for field, value in changes.items():
            if field != 'direction_ids':
                setattr(product, field, value)
        if directions is not None:
            product.directions = directions
        record_event(db, request, auth.user, 'it_product.update', entity_type='it_product', entity_id=product_id,
                     summary=f'Изменён ИТ-продукт «{product.vendor} — {product.name}»', payload=changes)
        commit_or_conflict(db)
    return product_out(db, product_id)


# ---------- universities, managers, users ----------

class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str


class UniversityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    short_name: str
    city: str
    region: str
    website: str
    contact: str
    is_active: bool
    managers: list[PersonOut]


def _website(value):
    value = (value or '').strip()
    if value and not value.lower().startswith(('http://', 'https://')):
        raise ValueError('Адрес сайта должен начинаться с http:// или https://')
    return value


class UniversityIn(BaseModel):
    name: Name
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    short_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ''
    region: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ''
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ''
    contact: ShortText = ''

    _check_website = field_validator('website')(_website)


class UniversityPatch(BaseModel):
    name: Name | None = None
    city: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    short_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    region: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    website: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None
    contact: ShortText | None = None
    is_active: bool | None = None

    @field_validator('website')
    @classmethod
    def check_website(cls, value):
        return None if value is None else _website(value)


class ManagersIn(BaseModel):
    user_ids: list[int] = Field(max_length=100)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    roles: list[str]
    is_active: bool


def university_out(db, university_id):
    return db.scalar(select(University).options(selectinload(University.managers)).where(University.id == university_id))


@router.get('/universities', response_model=list[UniversityOut], summary='Учебные заведения')
def list_universities(q: str | None = None, include_inactive: bool = False, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    query = (
        select(University).options(selectinload(University.managers))
        .where(university_scope(University.id, auth.user)).order_by(University.name)
    )
    if not include_inactive:
        query = query.where(University.is_active.is_(True))
    if q:
        pattern = like_pattern(q)
        query = query.where(or_(University.name.ilike(pattern, escape='\\'), University.short_name.ilike(pattern, escape='\\'), University.city.ilike(pattern, escape='\\')))
    return db.scalars(query).all()


@router.get('/universities/{university_id}', response_model=UniversityOut, summary='Учебное заведение')
def get_university(university_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    university_in_scope(db, auth.user, university_id)
    return university_out(db, university_id)


@router.post('/universities', response_model=UniversityOut, status_code=201, summary='Добавить учебное заведение')
def create_university(data: UniversityIn, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    university = University(**data.model_dump())
    db.add(university)
    flush_or_conflict(db)
    record_event(db, request, auth.user, 'university.create', entity_type='university', entity_id=university.id,
                 summary=f'Добавлено учебное заведение «{university.name}»', payload={'name': university.name, 'city': university.city})
    db.commit()
    return university_out(db, university.id)


@router.patch('/universities/{university_id}', response_model=UniversityOut, summary='Изменить учебное заведение')
def update_university(university_id: int, data: UniversityPatch, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    university = db.get(University, university_id)
    if university is None:
        raise not_found()
    changes = differing(university, data.model_dump(exclude_unset=True, exclude_none=True))
    if changes:
        for field, value in changes.items():
            setattr(university, field, value)
        record_event(db, request, auth.user, 'university.update', entity_type='university', entity_id=university_id,
                     summary=f'Изменено учебное заведение «{university.name}»', payload=changes)
        commit_or_conflict(db)
    return university_out(db, university_id)


@router.put('/universities/{university_id}/managers', response_model=UniversityOut, summary='Назначить ответственных от ИТ-школы')
def set_managers(university_id: int, data: ManagersIn, request: Request, auth: AuthContext = Depends(catalog_editor), db: Session = Depends(get_db)):
    university = db.get(University, university_id)
    if university is None:
        raise not_found()
    wanted = set(data.user_ids)
    users = db.scalars(select(User).where(User.id.in_(wanted), User.is_active.is_(True))).all() if wanted else []
    if len(users) != len(wanted):
        raise validation_error('user_ids', 'Указан несуществующий или неактивный пользователь')

    current = set(db.scalars(select(UniversityManager.user_id).where(UniversityManager.university_id == university_id)))
    added, removed = wanted - current, current - wanted
    if added or removed:
        with db.no_autoflush:
            for user_id in added:
                db.add(UniversityManager(university_id=university_id, user_id=user_id, assigned_by_user_id=auth.user.id))
            for assignment in db.scalars(select(UniversityManager).where(UniversityManager.university_id == university_id, UniversityManager.user_id.in_(removed))) if removed else []:
                db.delete(assignment)
        record_event(db, request, auth.user, 'university.managers', entity_type='university', entity_id=university_id,
                     summary=f'Изменены ответственные за «{university.name}»',
                     payload={'added': sorted(added), 'removed': sorted(removed)})
        commit_or_conflict(db)
    return university_out(db, university_id)


@router.get('/users', response_model=list[UserOut], summary='Пользователи CRM', dependencies=[Depends(catalog_editor)])
def list_users(role: Literal['crm-user', 'crm-supervisor', 'crm-admin'] | None = None, db: Session = Depends(get_db)):
    query = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    if role:
        query = query.where(User.roles.any(role))
    return db.scalars(query).all()


# ---------- university contacts ----------

class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    university_id: int
    full_name: str
    position: str
    email: str
    phone: str
    comment: str
    is_active: bool


def _email(value):
    value = (value or '').strip()
    if value and ('@' not in value or value.startswith('@') or value.endswith('@')):
        raise ValueError('Некорректный адрес электронной почты')
    return value


class ContactIn(BaseModel):
    full_name: Name
    position: ShortText = ''
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)] = ''
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ''
    comment: LongText = ''

    _check_email = field_validator('email')(_email)


class ContactPatch(BaseModel):
    full_name: Name | None = None
    position: ShortText | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    comment: LongText | None = None
    is_active: bool | None = None

    @field_validator('email')
    @classmethod
    def check_email(cls, value):
        return None if value is None else _email(value)


@router.get('/universities/{university_id}/contacts', response_model=list[ContactOut], summary='Ответственные от вуза')
def list_contacts(university_id: int, include_inactive: bool = False, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    university_in_scope(db, auth.user, university_id)
    query = select(UniversityContact).where(UniversityContact.university_id == university_id).order_by(UniversityContact.full_name)
    if not include_inactive:
        query = query.where(UniversityContact.is_active.is_(True))
    return db.scalars(query).all()


@router.post('/universities/{university_id}/contacts', response_model=ContactOut, status_code=201, summary='Добавить ответственного от вуза')
def create_contact(university_id: int, data: ContactIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    university = university_in_scope(db, auth.user, university_id)
    contact = UniversityContact(university_id=university_id, **data.model_dump())
    db.add(contact)
    flush_or_conflict(db)
    # Contacts are personal data (D-137): the audit trail references the record id, not the person's details.
    record_event(db, request, auth.user, 'university_contact.create', entity_type='university_contact', entity_id=contact.id,
                 summary=f'Добавлен ответственный от вуза «{university.name}»', payload={'university_id': university_id})
    db.commit()
    return contact


@router.patch('/university-contacts/{contact_id}', response_model=ContactOut, summary='Изменить ответственного от вуза')
def update_contact(contact_id: int, data: ContactPatch, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    contact = db.get(UniversityContact, contact_id)
    if contact is None:
        raise not_found()
    university = university_in_scope(db, auth.user, contact.university_id)
    changes = differing(contact, data.model_dump(exclude_unset=True, exclude_none=True))
    if changes:
        for field, value in changes.items():
            setattr(contact, field, value)
        record_event(db, request, auth.user, 'university_contact.update', entity_type='university_contact', entity_id=contact_id,
                     summary=f'Изменены данные ответственного от вуза «{university.name}»', payload={'fields': sorted(changes)})
        commit_or_conflict(db)
    return contact


# ---------- contracts ----------

TransferStatus = Literal['not_started', 'in_progress', 'transferred', 'cancelled']


class ProductRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vendor: str
    name: str


class ContractOut(BaseModel):
    id: int
    contract_number: str
    university: RefOut
    it_product: ProductRef
    signed_at: date
    valid_until: date
    transfer_status: str
    transfer_status_label: str
    manager: PersonOut | None
    manager_name: str
    contacts: list[PersonOut]
    comment: str
    is_expired: bool
    expires_soon: bool
    updated_at: datetime


class ContractPage(BaseModel):
    items: list[ContractOut]
    total: int
    limit: int
    offset: int


class ContractIn(BaseModel):
    contract_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    university_id: int = Field(gt=0)
    it_product_id: int = Field(gt=0)
    signed_at: date
    valid_until: date | None = None
    transfer_status: TransferStatus = 'not_started'
    manager_user_id: int | None = Field(default=None, gt=0)
    contact_ids: list[int] = Field(default_factory=list, max_length=50)
    comment: LongText = ''


class ContractPatch(BaseModel):
    contract_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    university_id: int | None = Field(default=None, gt=0)
    it_product_id: int | None = Field(default=None, gt=0)
    signed_at: date | None = None
    valid_until: date | None = None
    transfer_status: TransferStatus | None = None
    manager_user_id: int | None = Field(default=None, gt=0)
    contact_ids: list[int] | None = Field(default=None, max_length=50)
    comment: LongText | None = None


class StatusOut(BaseModel):
    value: str
    label: str


def contract_out(contract, today=None):
    today = today or date.today()
    return ContractOut(
        id=contract.id,
        contract_number=contract.contract_number,
        university=RefOut(id=contract.university.id, name=contract.university.name),
        it_product=ProductRef.model_validate(contract.it_product),
        signed_at=contract.signed_at,
        valid_until=contract.valid_until,
        transfer_status=contract.transfer_status,
        transfer_status_label=TRANSFER_STATUS_LABELS[contract.transfer_status],
        manager=PersonOut.model_validate(contract.manager) if contract.manager else None,
        manager_name=contract.manager_name,
        contacts=[PersonOut.model_validate(contact) for contact in contract.contacts],
        comment=contract.comment,
        is_expired=contract.valid_until < today,
        expires_soon=today <= contract.valid_until <= today + timedelta(days=EXPIRES_SOON_DAYS),
        updated_at=contract.updated_at,
    )


def contract_query():
    return select(Contract).options(
        selectinload(Contract.university), selectinload(Contract.it_product),
        selectinload(Contract.manager), selectinload(Contract.contacts),
    )


def contract_in_scope(db, user, contract_id):
    contract = db.scalar(contract_query().where(Contract.id == contract_id, university_scope(Contract.university_id, user)))
    if contract is None:
        raise not_found()
    return contract


def check_manager(db, user, manager_user_id):
    if manager_user_id is None:
        return
    if not sees_all(user):
        # One message for any other id, so managers cannot probe which user ids exist.
        if manager_user_id != user.id:
            raise validation_error('manager_user_id', 'Менеджер может указать ответственным по договору только себя')
        return
    if not db.scalar(select(exists().where(User.id == manager_user_id, User.is_active.is_(True)))):
        raise validation_error('manager_user_id', 'Указан несуществующий или неактивный пользователь')


def check_product(db, product_id, *, require_active):
    product = db.get(ITProduct, product_id)
    if product is None:
        raise validation_error('it_product_id', 'Указан несуществующий ИТ-продукт')
    if require_active and not product.is_active:
        raise validation_error('it_product_id', 'ИТ-продукт неактивен')
    return product


def load_contacts(db, university_id, contact_ids, *, newly_linked):
    unique_ids = set(contact_ids)
    contacts = db.scalars(select(UniversityContact).where(
        UniversityContact.id.in_(unique_ids), UniversityContact.university_id == university_id,
    )).all() if unique_ids else []
    if len(contacts) != len(unique_ids):
        raise validation_error('contact_ids', 'Ответственные должны относиться к выбранному учебному заведению')
    if any(not contact.is_active and contact.id in newly_linked for contact in contacts):
        raise validation_error('contact_ids', 'Нельзя привязать неактивного ответственного')
    return sorted(contacts, key=lambda contact: contact.full_name)


@router.get('/contracts/transfer-statuses', response_model=list[StatusOut], summary='Статусы передачи', dependencies=[Depends(any_role)])
def transfer_statuses():
    return [StatusOut(value=status, label=TRANSFER_STATUS_LABELS[status]) for status in TRANSFER_STATUSES]


@router.get('/contracts', response_model=ContractPage, summary='Договоры и лицензии')
def list_contracts(
    q: str | None = None,
    university_id: int | None = None,
    it_product_id: int | None = None,
    it_direction_id: int | None = None,
    manager_user_id: int | None = None,
    transfer_status: TransferStatus | None = None,
    signed_from: date | None = None,
    signed_to: date | None = None,
    valid_until_to: date | None = None,
    sort: Literal['signed_at', '-signed_at', 'valid_until', '-valid_until', 'contract_number'] = '-signed_at',
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    filters = [university_scope(Contract.university_id, auth.user)]
    if q:
        pattern = like_pattern(q)
        filters.append(or_(
            Contract.contract_number.ilike(pattern, escape='\\'),
            University.name.ilike(pattern, escape='\\'),
            ITProduct.name.ilike(pattern, escape='\\'),
            ITProduct.vendor.ilike(pattern, escape='\\'),
        ))
    if university_id is not None:
        filters.append(Contract.university_id == university_id)
    if it_product_id is not None:
        filters.append(Contract.it_product_id == it_product_id)
    if it_direction_id is not None:
        filters.append(exists().where(
            it_product_directions.c.it_product_id == Contract.it_product_id, it_product_directions.c.it_direction_id == it_direction_id,
        ))
    if manager_user_id is not None:
        filters.append(Contract.manager_user_id == manager_user_id)
    if transfer_status is not None:
        filters.append(Contract.transfer_status == transfer_status)
    if signed_from is not None:
        filters.append(Contract.signed_at >= signed_from)
    if signed_to is not None:
        filters.append(Contract.signed_at <= signed_to)
    if valid_until_to is not None:
        filters.append(Contract.valid_until <= valid_until_to)

    base = (
        select(Contract.id)
        .join(University, University.id == Contract.university_id)
        .join(ITProduct, ITProduct.id == Contract.it_product_id)
        .where(*filters)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    column = {'signed_at': Contract.signed_at, 'valid_until': Contract.valid_until, 'contract_number': Contract.contract_number}[sort.lstrip('-')]
    ordering = [column.desc() if sort.startswith('-') else column.asc(), Contract.id.desc()]
    ids = db.scalars(base.order_by(*ordering).limit(limit).offset(offset)).all()
    contracts = {contract.id: contract for contract in db.scalars(contract_query().where(Contract.id.in_(ids)))} if ids else {}
    today = date.today()
    return ContractPage(items=[contract_out(contracts[contract_id], today) for contract_id in ids], total=total, limit=limit, offset=offset)


@router.get('/contracts/{contract_id}', response_model=ContractOut, summary='Договор')
def get_contract(contract_id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    return contract_out(contract_in_scope(db, auth.user, contract_id))


@router.post('/contracts', response_model=ContractOut, status_code=201, summary='Добавить договор')
def create_contract(data: ContractIn, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    valid_until = data.valid_until or one_year_after(data.signed_at)
    if valid_until < data.signed_at:
        raise validation_error('valid_until', 'Срок действия не может закончиться раньше подписания')
    university = active_university_in_scope(db, auth.user, data.university_id)
    check_product(db, data.it_product_id, require_active=True)
    manager_user_id = data.manager_user_id
    if manager_user_id is None and not sees_all(auth.user):
        manager_user_id = auth.user.id
    check_manager(db, auth.user, manager_user_id)
    contacts = load_contacts(db, data.university_id, data.contact_ids, newly_linked=set(data.contact_ids))

    contract = Contract(
        contract_number=data.contract_number, university_id=data.university_id, it_product_id=data.it_product_id,
        signed_at=data.signed_at, valid_until=valid_until, transfer_status=data.transfer_status,
        manager_user_id=manager_user_id, comment=data.comment, contacts=contacts,
    )
    db.add(contract)
    flush_or_conflict(db)
    record_event(db, request, auth.user, 'contract.create', entity_type='contract', entity_id=contract.id,
                 summary=f'Добавлен договор № {contract.contract_number} с «{university.name}»',
                 payload={**data.model_dump(mode='json'), 'valid_until': valid_until.isoformat(), 'manager_user_id': manager_user_id})
    db.commit()
    return contract_out(contract_in_scope(db, auth.user, contract.id))


@router.patch('/contracts/{contract_id}', response_model=ContractOut, summary='Изменить договор')
def update_contract(contract_id: int, data: ContractPatch, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    contract = contract_in_scope(db, auth.user, contract_id)
    submitted = data.model_dump(exclude_unset=True)
    for field in ('contract_number', 'university_id', 'it_product_id', 'signed_at', 'valid_until', 'transfer_status', 'contact_ids', 'comment'):
        if field in submitted and submitted[field] is None:
            raise validation_error(field, 'Поле не может быть пустым')

    current_contact_ids = {contact.id for contact in contract.contacts}
    university_changed = 'university_id' in submitted and submitted['university_id'] != contract.university_id
    if university_changed:
        active_university_in_scope(db, auth.user, submitted['university_id'])
    if 'it_product_id' in submitted and submitted['it_product_id'] != contract.it_product_id:
        check_product(db, submitted['it_product_id'], require_active=True)
    if 'manager_user_id' in submitted and submitted['manager_user_id'] != contract.manager_user_id:
        check_manager(db, auth.user, submitted['manager_user_id'])

    university_id = submitted.get('university_id', contract.university_id)
    # Contacts belong to one university; moving the contract drops them unless new ones are sent.
    contact_ids = submitted.get('contact_ids', [] if university_changed else sorted(current_contact_ids))
    contacts = load_contacts(db, university_id, contact_ids, newly_linked=set(contact_ids) - current_contact_ids)

    signed_at = submitted.get('signed_at', contract.signed_at)
    valid_until = submitted.get('valid_until', contract.valid_until)
    if valid_until < signed_at:
        raise validation_error('valid_until', 'Срок действия не может закончиться раньше подписания')

    changes = differing(contract, {key: value for key, value in submitted.items() if key != 'contact_ids'})
    if {contact.id for contact in contacts} != current_contact_ids:
        changes['contact_ids'] = sorted(contact.id for contact in contacts)
    if not changes:
        return contract_out(contract)

    for field, value in changes.items():
        if field != 'contact_ids':
            setattr(contract, field, value)
    contract.contacts = contacts
    if 'manager_user_id' in changes:
        contract.manager_name = ''
    record_event(db, request, auth.user, 'contract.update', entity_type='contract', entity_id=contract_id,
                 summary=f'Изменён договор № {contract.contract_number}',
                 payload={key: (value.isoformat() if isinstance(value, date) else value) for key, value in changes.items()})
    commit_or_conflict(db)
    return contract_out(contract_in_scope(db, auth.user, contract_id))
