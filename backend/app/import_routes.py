"""Catalog upload API (contract: docs/api/imports.md; rules: docs/design/import.md, decisions D-142–D-146)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import importer
from .audit import record_event
from .auth import ROLE_ADMIN, ROLE_SUPERVISOR, AuthContext, require_roles
from .catalog_routes import PersonOut
from .db import get_db
from .errors import AppError, ErrorCode
from .importer import FIELD_LABELS, FIELDS, ImportFileError, UnsupportedFileType, interpret_row, name_key, read_upload, suggest_mapping, validate_mapping
from .models import CatalogImport, Contract, ITDirection, ITProduct, University, UniversityContact, User, utcnow

router = APIRouter(prefix='/api/v1/imports', tags=['Загрузка справочников'])
importer_role = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)
PREVIEW_ROWS = 20
HISTORY_SIZE = 20


class FieldOut(BaseModel):
    name: str
    label: str
    required: bool


class MappingIn(BaseModel):
    mapping: dict[str, str | None]


class PreviewRow(BaseModel):
    row_number: int
    cells: list


class ImportOut(BaseModel):
    id: int
    filename: str
    status: str
    header_row: int
    headers: list[str]
    mapping: dict[str, str | None]
    row_count: int
    preview: list[PreviewRow]
    created_at: datetime
    created_by: PersonOut | None
    report: dict | None


class ImportListItem(BaseModel):
    id: int
    filename: str
    status: str
    row_count: int
    created_at: datetime
    created_by: PersonOut | None
    applied_at: datetime | None
    summary: dict | None


# Parsed rows are stored as JSON; dates are tagged so they survive the round trip.
def _to_json(value):
    if isinstance(value, datetime):
        return {'$date': value.date().isoformat()}
    if isinstance(value, date):
        return {'$date': value.isoformat()}
    return value


def _from_json(value):
    if isinstance(value, dict) and '$date' in value:
        return date.fromisoformat(value['$date'])
    return value


def _display(value):
    value = _from_json(value)
    return value.isoformat() if isinstance(value, date) else value


def _import_out(record, db):
    creator = db.get(User, record.created_by_user_id) if record.created_by_user_id else None
    return ImportOut(
        id=record.id,
        filename=record.filename,
        status=record.status,
        header_row=record.header_row,
        headers=record.headers,
        mapping=record.mapping or record.suggested_mapping,
        row_count=len(record.rows),
        preview=[PreviewRow(row_number=number, cells=[_display(cell) for cell in cells]) for number, cells in record.rows[:PREVIEW_ROWS]],
        created_at=record.created_at,
        created_by=PersonOut(id=creator.id, full_name=creator.full_name) if creator else None,
        report=record.report,
    )


def _load(db, import_id, *, lock=False):
    query = select(CatalogImport).where(CatalogImport.id == import_id)
    if lock:
        query = query.with_for_update()
    record = db.scalar(query)
    if record is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    return record


def _checked_mapping(record, mapping):
    problems = validate_mapping(record.headers, mapping)
    if problems:
        raise AppError(ErrorCode.VALIDATION_ERROR, problems[0], [{'field': 'mapping', 'message': problem} for problem in problems])
    return {field: mapping.get(field) for field in FIELDS}


@router.get('/fields', response_model=list[FieldOut], summary='Поля CRM для сопоставления', dependencies=[Depends(importer_role)])
def import_fields():
    return [FieldOut(name=name, label=FIELD_LABELS[name], required=required) for name, (required, _, _) in FIELDS.items()]


@router.get('', response_model=list[ImportListItem], summary='История загрузок', dependencies=[Depends(importer_role)])
def list_imports(db: Session = Depends(get_db)):
    records = db.scalars(select(CatalogImport).order_by(CatalogImport.created_at.desc(), CatalogImport.id.desc()).limit(HISTORY_SIZE)).all()
    creators = {user.id: user for user in db.scalars(select(User).where(User.id.in_({r.created_by_user_id for r in records if r.created_by_user_id})))}
    return [
        ImportListItem(
            id=record.id, filename=record.filename, status=record.status, row_count=len(record.rows),
            created_at=record.created_at, applied_at=record.applied_at,
            created_by=PersonOut(id=creators[record.created_by_user_id].id, full_name=creators[record.created_by_user_id].full_name) if record.created_by_user_id in creators else None,
            summary=(record.report or {}).get('summary'),
        )
        for record in records
    ]


@router.post('', response_model=ImportOut, status_code=201, summary='Загрузить файл xls/xlsx')
def upload(request: Request, file: UploadFile = File(...), auth: AuthContext = Depends(importer_role), db: Session = Depends(get_db)):
    # Read one byte past the limit to detect oversize files without loading arbitrarily large uploads.
    content = file.file.read(importer.MAX_FILE_BYTES + 1)
    if len(content) > importer.MAX_FILE_BYTES:
        raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, 'Файл больше 10 МБ')
    filename = (file.filename or 'upload').replace('\\', '/').rsplit('/', 1)[-1][:255]
    try:
        sheet = read_upload(filename, content)
    except UnsupportedFileType as error:
        raise AppError(ErrorCode.UNSUPPORTED_MEDIA_TYPE, str(error), [{'field': 'file', 'message': str(error)}]) from error
    except ImportFileError as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, str(error), [{'field': 'file', 'message': str(error)}]) from error

    record = CatalogImport(
        created_by_user_id=auth.user.id,
        filename=filename,
        header_row=sheet.header_row,
        headers=sheet.headers,
        rows=[[number, [_to_json(cell) for cell in cells]] for number, cells in sheet.rows],
        suggested_mapping=suggest_mapping(sheet.headers),
        status='uploaded',
    )
    db.add(record)
    db.commit()
    return _import_out(record, db)


@router.get('/{import_id}', response_model=ImportOut, summary='Загрузка и её отчёт', dependencies=[Depends(importer_role)])
def get_import(import_id: int, db: Session = Depends(get_db)):
    return _import_out(_load(db, import_id), db)


@router.post('/{import_id}/check', summary='Проверить загрузку без записи', dependencies=[Depends(importer_role)])
def check_import(import_id: int, data: MappingIn, db: Session = Depends(get_db)):
    record = _load(db, import_id)
    mapping = _checked_mapping(record, data.mapping)
    report = CatalogWriter(db, apply=False).run(record, mapping)
    db.rollback()
    return report


@router.post('/{import_id}/apply', summary='Применить загрузку')
def apply_import(import_id: int, data: MappingIn, request: Request, auth: AuthContext = Depends(importer_role), db: Session = Depends(get_db)):
    record = _load(db, import_id, lock=True)
    if record.status == 'applied':
        raise AppError(ErrorCode.CONFLICT, 'Эта загрузка уже применена')
    mapping = _checked_mapping(record, data.mapping)
    report = CatalogWriter(db, apply=True).run(record, mapping)
    record.status = 'applied'
    record.mapping = mapping
    record.report = report
    record.applied_at = utcnow()
    record_event(db, request, auth.user, 'import.apply', entity_type='catalog_import', entity_id=record.id,
                 summary=f'Применена загрузка «{record.filename}»: строк {report["summary"]["valid"]} из {report["summary"]["rows"]}',
                 payload={'filename': record.filename, 'summary': report['summary']})
    db.commit()
    return report


class CatalogWriter:
    """Interprets rows and either plans (check) or performs (apply) catalog changes within one transaction."""

    def __init__(self, db, *, apply):
        self.db = db
        self.apply = apply
        self.created = {'universities': 0, 'it_products': 0, 'it_directions': 0, 'university_contacts': 0, 'contracts': 0}
        self.updated = {'contracts': 0}

    def run(self, record, mapping):
        headers = record.headers
        positions = {field: headers.index(header) for field, header in mapping.items() if header}
        results = []
        for number, cells in record.rows:
            raw = {field: _from_json(cells[position]) if position < len(cells) else None for field, position in positions.items()}
            results.append(interpret_row(number, raw))

        # When a contract number repeats, the last row wins and earlier ones are reported as skipped.
        last_row = {}
        for result in results:
            if result.is_valid:
                last_row[result.values['contract_number']] = result.row_number
        self._load_caches(results)

        rows = []
        for result in results:
            entry = {'row_number': result.row_number, 'contract_number': result.values.get('contract_number', ''), 'action': None}
            if not result.is_valid:
                entry.update(status='error', errors=result.errors, warnings=result.warnings)
            elif last_row[result.values['contract_number']] != result.row_number:
                entry.update(status='skipped', errors=[], warnings=['Номер договора повторяется ниже в файле; применяется последняя строка'])
            else:
                entry['action'] = self._write_row(result, mapping)
                entry.update(status='warning' if result.warnings else 'ok', errors=[], warnings=result.warnings)
            rows.append(entry)

        statuses = [row['status'] for row in rows]
        return {
            'summary': {
                'rows': len(rows),
                'valid': statuses.count('ok') + statuses.count('warning'),
                'invalid': statuses.count('error'),
                'skipped': statuses.count('skipped'),
                'with_warnings': statuses.count('warning'),
                'created': self.created,
                'updated': self.updated,
            },
            'rows': rows,
        }

    def _load_caches(self, results):
        db = self.db
        self.universities = {name_key(university.name): university for university in db.scalars(select(University))}
        self.products = {(name_key(product.vendor), name_key(product.name)): product for product in db.scalars(select(ITProduct).options(selectinload(ITProduct.directions)))}
        self.directions = {name_key(direction.name): direction for direction in db.scalars(select(ITDirection))}
        users_by_name = {}
        for user in db.scalars(select(User).where(User.is_active.is_(True))):
            users_by_name.setdefault(name_key(user.full_name), []).append(user)
        self.users_by_name = users_by_name
        numbers = {result.values['contract_number'] for result in results if result.is_valid}
        self.contracts = {contract.contract_number: contract for contract in db.scalars(
            select(Contract).options(selectinload(Contract.contacts)).where(Contract.contract_number.in_(numbers))
        )} if numbers else {}
        self.contacts = {}
        for contact in db.scalars(select(UniversityContact)):
            self.contacts[(contact.university_id, name_key(contact.full_name))] = contact
        # Keys of records that a dry run would create, so counts are not repeated for later rows.
        self.planned = set()

    def _university(self, result):
        name = result.values['university_name']
        key = name_key(name)
        if key in self.universities:
            return self.universities[key]
        result.warnings.append(f'Учебное заведение «{name}» будет создано без города')
        if not self.apply:
            if ('university', key) not in self.planned:
                self.planned.add(('university', key))
                self.created['universities'] += 1
            return None
        university = University(name=name, city='', contact='')
        self.db.add(university)
        self.db.flush()
        self.universities[key] = university
        self.created['universities'] += 1
        return university

    def _direction(self, name):
        key = name_key(name)
        if key in self.directions:
            return self.directions[key]
        if not self.apply:
            if ('direction', key) not in self.planned:
                self.planned.add(('direction', key))
                self.created['it_directions'] += 1
            return None
        direction = ITDirection(name=name)
        self.db.add(direction)
        self.db.flush()
        self.directions[key] = direction
        self.created['it_directions'] += 1
        return direction

    def _product(self, result):
        vendor, name = result.values['vendor'], result.values['software']
        key = (name_key(vendor), name_key(name))
        product = self.products.get(key)
        directions = [self._direction(direction_name) for direction_name in result.values['it_directions']]
        if product is None:
            if not self.apply:
                if ('product', key) not in self.planned:
                    self.planned.add(('product', key))
                    self.created['it_products'] += 1
                return None
            product = ITProduct(vendor=vendor, name=name, directions=[direction for direction in directions if direction])
            self.db.add(product)
            self.db.flush()
            self.products[key] = product
            self.created['it_products'] += 1
            return product
        if self.apply:
            known = {direction.id for direction in product.directions}
            for direction in directions:
                if direction is not None and direction.id not in known:
                    product.directions.append(direction)
        return product

    def _contacts(self, university, result):
        contacts = []
        for full_name in result.values['university_contacts']:
            key = (university.id if university else None, name_key(full_name))
            contact = self.contacts.get(key) if university else None
            if contact is None:
                if not self.apply:
                    if ('contact', key, result.values['university_name']) not in self.planned:
                        self.planned.add(('contact', key, result.values['university_name']))
                        self.created['university_contacts'] += 1
                    continue
                contact = UniversityContact(university_id=university.id, full_name=full_name)
                self.db.add(contact)
                self.db.flush()
                self.contacts[key] = contact
                self.created['university_contacts'] += 1
            contacts.append(contact)
        return contacts

    def _manager(self, result):
        name = result.values['manager_full_name']
        if not name:
            return None, ''
        matches = self.users_by_name.get(name_key(name), [])
        if len(matches) == 1:
            return matches[0].id, ''
        reason = 'найдено несколько пользователей с таким ФИО' if matches else 'не найден среди пользователей CRM'
        result.warnings.append(f'Менеджер «{name}» {reason}; ФИО сохранено текстом')
        return None, name

    def _write_row(self, result, mapping):
        values = result.values
        university = self._university(result)
        product = self._product(result)
        manager_user_id, manager_name = self._manager(result)
        contacts = self._contacts(university, result)
        contract = self.contracts.get(values['contract_number'])
        action = 'update' if contract is not None else 'create'

        if not self.apply:
            if action == 'create':
                if ('contract', values['contract_number']) not in self.planned:
                    self.planned.add(('contract', values['contract_number']))
                    self.created['contracts'] += 1
            else:
                self.updated['contracts'] += 1
            return action

        if contract is None:
            contract = Contract(contract_number=values['contract_number'])
            self.db.add(contract)
            self.contracts[values['contract_number']] = contract
            self.created['contracts'] += 1
        else:
            self.updated['contracts'] += 1
        moved = contract.university_id is not None and contract.university_id != university.id
        contract.university_id = university.id
        contract.it_product_id = product.id
        contract.signed_at = values['license_signed_at']
        contract.valid_until = values['license_valid_until']
        contract.transfer_status = values['transfer_status']
        if mapping.get('manager_full_name'):
            contract.manager_user_id, contract.manager_name = manager_user_id, manager_name
        if values['comment'] or action == 'create':
            contract.comment = values['comment']
        if mapping.get('university_contacts') or moved:
            contract.contacts = contacts
        self.db.flush()
        return action
