"""Supplier company and product-contact catalog API."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import _email, commit_or_conflict, flush_or_conflict, like_pattern, not_found, validation_error
from .db import get_db
from .models import ITProduct, VendorCompany, VendorContact, vendor_contact_products

router = APIRouter(prefix='/api/v1', tags=['Компании-поставщики'])
viewer = require_roles(*ALL_ROLES)
editor = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Channel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class CompanyIn(BaseModel):
    name: Name


class CompanyPatch(BaseModel):
    name: Name | None = None
    is_active: bool | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool


class ContactIn(BaseModel):
    company_id: int
    full_name: Name
    phone: Phone = ''
    email: Email = ''
    preferred_channels: list[Channel] = Field(default_factory=list, max_length=10)
    product_ids: list[int] = Field(min_length=1, max_length=50)

    _check_email = field_validator('email')(_email)


class ContactPatch(BaseModel):
    full_name: Name | None = None
    phone: Phone | None = None
    email: Email | None = None
    preferred_channels: list[Channel] | None = Field(default=None, max_length=10)
    product_ids: list[int] | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None

    @field_validator('email')
    @classmethod
    def check_email(cls, value):
        return None if value is None else _email(value)


class ContactOut(BaseModel):
    id: int
    company_id: int
    full_name: str
    phone: str
    email: str
    preferred_channels: list[str]
    product_ids: list[int]
    is_active: bool


def contact_out(contact):
    return ContactOut(
        id=contact.id, company_id=contact.company_id, full_name=contact.full_name,
        phone=contact.phone, email=contact.email, preferred_channels=contact.preferred_channels,
        product_ids=[product.id for product in contact.products], is_active=contact.is_active,
    )


def load_products(db, company_id, ids):
    unique_ids = set(ids)
    products = db.scalars(select(ITProduct).where(ITProduct.id.in_(unique_ids))).all()
    if len(products) != len(unique_ids) or any(product.company_id != company_id for product in products):
        raise validation_error('product_ids', 'Укажите продукты этой компании')
    return sorted(products, key=lambda product: product.name)


@router.get('/vendor-companies', response_model=list[CompanyOut], dependencies=[Depends(viewer)])
def list_companies(q: str | None = None, product_id: int | None = None, include_inactive: bool = False,
                   db: Session = Depends(get_db)):
    query = select(VendorCompany).order_by(VendorCompany.name)
    if not include_inactive:
        query = query.where(VendorCompany.is_active.is_(True))
    if q:
        query = query.where(VendorCompany.name.ilike(like_pattern(q), escape='\\'))
    if product_id is not None:
        query = query.where(exists().where(ITProduct.company_id == VendorCompany.id, ITProduct.id == product_id))
    return db.scalars(query).all()


@router.get('/vendor-companies/{company_id}', response_model=CompanyOut, dependencies=[Depends(viewer)])
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.get(VendorCompany, company_id)
    if company is None:
        raise not_found()
    return company


@router.post('/vendor-companies', response_model=CompanyOut, status_code=201)
def create_company(data: CompanyIn, request: Request, auth: AuthContext = Depends(editor), db: Session = Depends(get_db)):
    company = VendorCompany(name=data.name)
    db.add(company)
    flush_or_conflict(db)
    record_event(db, request, auth.user, 'vendor_company.create', entity_type='vendor_company', entity_id=company.id,
                 summary=f'Добавлена компания «{company.name}»', payload={})
    db.commit()
    return company


@router.patch('/vendor-companies/{company_id}', response_model=CompanyOut)
def update_company(company_id: int, data: CompanyPatch, request: Request,
                   auth: AuthContext = Depends(editor), db: Session = Depends(get_db)):
    company = db.get(VendorCompany, company_id)
    if company is None:
        raise not_found()
    changes = {key: value for key, value in data.model_dump(exclude_unset=True, exclude_none=True).items()
               if getattr(company, key) != value}
    if changes:
        if 'name' in changes:
            for product in company.products:
                product.vendor = changes['name']
        for key, value in changes.items():
            setattr(company, key, value)
        record_event(db, request, auth.user, 'vendor_company.update', entity_type='vendor_company', entity_id=company_id,
                     summary=f'Изменена компания «{company.name}»', payload={'fields': sorted(changes)})
        commit_or_conflict(db)
    return company


@router.get('/vendor-contacts', response_model=list[ContactOut], dependencies=[Depends(viewer)])
def list_contacts(company_id: int | None = None, product_id: int | None = None, q: str | None = None,
                  include_inactive: bool = False, db: Session = Depends(get_db)):
    query = select(VendorContact).options(selectinload(VendorContact.products)).order_by(VendorContact.full_name, VendorContact.id)
    if not include_inactive:
        query = query.where(VendorContact.is_active.is_(True))
    if company_id is not None:
        query = query.where(VendorContact.company_id == company_id)
    if product_id is not None:
        query = query.where(exists().where(
            vendor_contact_products.c.vendor_contact_id == VendorContact.id,
            vendor_contact_products.c.it_product_id == product_id,
        ))
    if q:
        pattern = like_pattern(q)
        query = query.where(or_(VendorContact.full_name.ilike(pattern, escape='\\'),
                                VendorContact.email.ilike(pattern, escape='\\'),
                                VendorContact.phone.ilike(pattern, escape='\\')))
    return [contact_out(contact) for contact in db.scalars(query).all()]


@router.get('/vendor-contacts/{contact_id}', response_model=ContactOut, dependencies=[Depends(viewer)])
def get_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.scalar(select(VendorContact).options(selectinload(VendorContact.products)).where(VendorContact.id == contact_id))
    if contact is None:
        raise not_found()
    return contact_out(contact)


@router.post('/vendor-contacts', response_model=ContactOut, status_code=201)
def create_contact(data: ContactIn, request: Request, auth: AuthContext = Depends(editor), db: Session = Depends(get_db)):
    company = db.get(VendorCompany, data.company_id)
    if company is None or not company.is_active:
        raise validation_error('company_id', 'Компания не найдена или отключена')
    products = load_products(db, company.id, data.product_ids)
    contact = VendorContact(company=company, full_name=data.full_name, phone=data.phone, email=data.email,
                            preferred_channels=data.preferred_channels, products=products)
    db.add(contact)
    db.flush()
    record_event(db, request, auth.user, 'vendor_contact.create', entity_type='vendor_contact', entity_id=contact.id,
                 summary='Добавлен контакт компании', payload={'company_id': company.id})
    db.commit()
    return contact_out(contact)


@router.patch('/vendor-contacts/{contact_id}', response_model=ContactOut)
def update_contact(contact_id: int, data: ContactPatch, request: Request,
                   auth: AuthContext = Depends(editor), db: Session = Depends(get_db)):
    contact = db.scalar(select(VendorContact).options(selectinload(VendorContact.products)).where(VendorContact.id == contact_id))
    if contact is None:
        raise not_found()
    submitted = data.model_dump(exclude_unset=True, exclude_none=True)
    product_ids = submitted.pop('product_ids', None)
    products = load_products(db, contact.company_id, product_ids) if product_ids is not None else None
    changes = {key: value for key, value in submitted.items() if getattr(contact, key) != value}
    if products is not None and {item.id for item in products} != {item.id for item in contact.products}:
        changes['product_ids'] = [item.id for item in products]
    if changes:
        for key, value in submitted.items():
            if key in changes:
                setattr(contact, key, value)
        if products is not None:
            contact.products = products
        record_event(db, request, auth.user, 'vendor_contact.update', entity_type='vendor_contact', entity_id=contact_id,
                     summary='Изменён контакт компании', payload={'fields': sorted(changes)})
        db.commit()
    return contact_out(contact)
