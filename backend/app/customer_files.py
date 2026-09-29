"""The customer's files in «Загрузка справочников» (owner 29.09.2026, D-247; sheet map: docs/design/customer-files-import.md).

Two importers next to the column import, chosen by the file's content:

* the applications JSON — only the application number, course and stream are read; names, phones and e-mails are
  dropped here, before anything is stored, and no payment state is inferred;
* the customer workbook — read by sheet name. «Вузы» updates existing universities only, «Направления» and
  «Продукты РТК» update or create IT directions and products; every other sheet is listed with the reason it is
  not imported.
"""
import io
import json
import zipfile
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy import select

from .importer import HEADER_SEARCH_ROWS, MAX_DATA_ROWS, XLSX_SIGNATURE, ImportFileError, name_key
from .models import CourseApplication, ITDirection, ITProduct, University, VendorCompany

APPLICATION_FIELDS = (('number', 'Номер заявки', 100), ('course', 'Курс', 200), ('stream', 'Номер потока', 100))
APPLICATION_HEADERS = [label for _, label, _ in APPLICATION_FIELDS]
WORKBOOK_MARKERS = {'Вузы', 'Продукты РТК'}
RTK_VENDOR = 'ПАО «Ростелеком»'


@dataclass(frozen=True)
class SupportedSheet:
    key: str
    columns: dict  # CRM field -> header in the workbook
    max_lengths: dict = field(default_factory=dict)


SUPPORTED_SHEETS = {
    'Вузы': SupportedSheet('university_id', {
        'full_name': 'Полное наименование', 'short_name': 'Краткое наименование', 'region': 'Регион',
        'city': 'Город', 'website': 'Официальный сайт'}, {'short_name': 100, 'region': 100, 'city': 100, 'website': 300}),
    'Направления': SupportedSheet('direction_id', {'name': 'Направление', 'description': 'Содержание'}, {'name': 120}),
    'Продукты РТК': SupportedSheet('product_id', {'name': 'Наименование', 'description': 'Описание'}, {'name': 200}),
}
NO_ENTITY = 'В CRM нет сущности для этих данных; лист не загружается'
UNSUPPORTED_SHEETS = {
    'Программы': NO_ENTITY + ' (программа вуза хранится только текстом во взаимодействии)',
    'Договоры': 'Шаблон не заполнен (нет номеров и дат), а договор CRM связан с одним продуктом; лист не загружается',
    'Продукты договора': 'Шаблон не заполнен; связь договоров с продуктами не утверждена; лист не загружается',
    'Ответственные': 'Шаблон не заполнен (нет сотрудников); лист не загружается',
    'Допсоглашения': NO_ENTITY,
    'Источники': NO_ENTITY,
}
SERVICE_SHEETS = {'Сводка', 'Справочники', 'Инструкция'}


def detect_kind(filename, content):
    """'applications' for a JSON array, 'workbook' for the customer workbook, otherwise 'catalog' (the column import)."""
    head = content[:64].lstrip(b'\xef\xbb\xbf \t\r\n')
    if filename.lower().endswith('.json') or head.startswith(b'['):
        return 'applications'
    if content.startswith(XLSX_SIGNATURE):
        try:
            names = set(openpyxl.load_workbook(io.BytesIO(content), read_only=True).sheetnames)
        except (zipfile.BadZipFile, KeyError, OSError, ValueError):
            return 'catalog'  # the column import reports the damaged file as before
        if WORKBOOK_MARKERS <= names:
            return 'workbook'
    return 'catalog'


# ---- applications JSON -----------------------------------------------------------------------------------------

def _kept(value):
    # Only plain values are kept; lists or objects in these fields are reported, not stored.
    return value if isinstance(value, (str, int, float, bool)) or value is None else {'$invalid': type(value).__name__}


def read_applications(content):
    """Rows as [entry number, [number, course, stream] | None | '$not_object']; personal fields are never read."""
    try:
        entries = json.loads(content.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImportFileError('Файл не является корректным JSON') from error
    if not isinstance(entries, list):
        raise ImportFileError('Ожидается JSON-массив заявок')
    if len(entries) > MAX_DATA_ROWS:
        raise ImportFileError(f'В файле больше {MAX_DATA_ROWS} записей')
    objects = [entry for entry in entries if isinstance(entry, dict)]
    if not any(label in entry for entry in objects for label in APPLICATION_HEADERS):
        raise ImportFileError('В файле нет полей «Номер заявки», «Курс», «Номер потока»')
    rows = []
    for number, entry in enumerate(entries, start=1):
        if entry is None:
            rows.append([number, None])
        elif not isinstance(entry, dict):
            rows.append([number, '$not_object'])
        else:
            rows.append([number, [_kept(entry.get(label)) for label in APPLICATION_HEADERS]])
    return rows


def application_preview(cells):
    if not isinstance(cells, list):
        return [None, None, None]
    return [None if isinstance(value, dict) else (str(value) if value is not None else None) for value in cells]


def _application_values(cells):
    """(values, error) for one stored entry."""
    values, problems = {}, []
    for (name, label, max_length), value in zip(APPLICATION_FIELDS, cells):
        if name == 'stream' and isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str) or not value.strip():
            problems.append(f'Нет или неверное значение «{label}»')
            continue
        value = value.strip()
        if len(value) > max_length:
            problems.append(f'«{label}» длиннее {max_length} символов')
            continue
        values[name] = value
    return values, problems


class ApplicationWriter:
    """Plans (check) or writes (apply) course applications matched by application number."""

    def __init__(self, db, *, apply):
        self.db = db
        self.apply = apply

    def run(self, record):
        interpreted = []
        for number, cells in record.rows:
            if cells is None:
                interpreted.append((number, None, [], ['Пустая запись (null) пропущена']))
            elif cells == '$not_object':
                interpreted.append((number, None, ['Запись не является объектом JSON'], []))
            else:
                values, errors = _application_values(cells)
                interpreted.append((number, values if not errors else None, errors, []))
        last = {values['number']: number for number, values, _, _ in interpreted if values}
        existing = {row.external_number: row for row in self.db.scalars(
            select(CourseApplication).where(CourseApplication.external_number.in_(set(last))))} if last else {}
        created = updated = 0
        rows = []
        for number, values, errors, warnings in interpreted:
            entry = {'row_number': number, 'key': values['number'] if values else '', 'action': None,
                     'errors': errors, 'warnings': warnings}
            if errors:
                entry['status'] = 'error'
            elif values is None:
                entry['status'] = 'skipped'
            elif last[values['number']] != number:
                entry.update(status='skipped', warnings=['Номер заявки повторяется ниже в файле; применяется последняя запись'])
            else:
                application = existing.get(values['number'])
                if application is None:
                    entry['action'] = 'create'
                    created += 1
                    if self.apply:
                        self.db.add(CourseApplication(external_number=values['number'], course=values['course'],
                                                      stream_number=values['stream']))
                elif (application.course, application.stream_number) != (values['course'], values['stream']):
                    entry['action'] = 'update'
                    updated += 1
                    if self.apply:
                        application.course, application.stream_number = values['course'], values['stream']
                else:
                    entry['action'] = 'unchanged'
                entry['status'] = 'ok'
            rows.append(entry)
        if self.apply:
            self.db.flush()
        return _report(rows, {'course_applications': created}, {'course_applications': updated})


# ---- customer workbook -----------------------------------------------------------------------------------------

def _text(value):
    return '' if value is None else str(value).strip()


def _rows_below_header(data_rows):
    # The header is the first row with at least two filled cells; title lines above it are not data.
    for position, (_, row) in enumerate(data_rows):
        if sum(1 for cell in row if _text(cell)) >= 2:
            return len(data_rows) - position - 1
    return 0


def read_workbook(content):
    """(sheets overview, rows of the supported sheets). Unsupported sheets are listed with a reason, never read."""
    try:
        book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise ImportFileError('Файл .xlsx повреждён') from error
    sheets, rows = [], []
    try:
        for sheet in book.worksheets:
            data_rows = [(index, row) for index, row in enumerate(sheet.iter_rows(values_only=True), start=1)
                         if any(_text(cell) for cell in row)]
            if sheet.title in SUPPORTED_SHEETS:
                spec = SUPPORTED_SHEETS[sheet.title]
                header = next(((index, [_text(cell) for cell in row]) for index, row in data_rows[:HEADER_SEARCH_ROWS]
                               if spec.key in [_text(cell) for cell in row]), None)
                wanted = [spec.key, *spec.columns.values()]
                if header is None or any(column not in header[1] for column in wanted):
                    sheets.append({'name': sheet.title, 'status': 'error', 'rows': 0,
                                   'reason': 'Не найдены столбцы: ' + ', '.join(c for c in wanted if header is None or c not in header[1])})
                    continue
                header_row, headers = header
                positions = {name: headers.index(column) for name, column in [('key', spec.key), *spec.columns.items()]}
                count = 0
                for index, row in data_rows:
                    if index <= header_row:
                        continue
                    cells = list(row)
                    rows.append({'sheet': sheet.title, 'row': index,
                                 'values': {name: _text(cells[pos]) if pos < len(cells) else '' for name, pos in positions.items()}})
                    count += 1
                if len(rows) > MAX_DATA_ROWS:
                    raise ImportFileError(f'В файле больше {MAX_DATA_ROWS} строк')
                sheets.append({'name': sheet.title, 'status': 'supported', 'rows': count, 'reason': ''})
            elif sheet.title in SERVICE_SHEETS:
                sheets.append({'name': sheet.title, 'status': 'service', 'rows': _rows_below_header(data_rows),
                               'reason': 'Служебный лист книги; не загружается'})
            else:
                sheets.append({'name': sheet.title, 'status': 'not_supported', 'rows': _rows_below_header(data_rows),
                               'reason': UNSUPPORTED_SHEETS.get(sheet.title, 'Лист не распознан; не загружается')})
    finally:
        book.close()
    return sheets, rows


class WorkbookWriter:
    """Plans (check) or writes (apply) the supported workbook sheets by their stable IDs."""

    def __init__(self, db, *, apply):
        self.db = db
        self.apply = apply
        self.created = {'universities': 0, 'it_directions': 0, 'it_products': 0}
        self.updated = {'universities': 0, 'it_directions': 0, 'it_products': 0}
        self.unmatched = []

    def run(self, record):
        db = self.db
        universities = list(db.scalars(select(University).where(University.is_active.is_(True))))
        self.university_by_id = {u.external_id: u for u in db.scalars(select(University)) if u.external_id}
        self.university_by_name = {}
        for university in universities:
            for name in (university.name, university.short_name):
                if name:
                    self.university_by_name.setdefault(name_key(name), university)
        self.directions = list(db.scalars(select(ITDirection)))
        self.products = list(db.scalars(select(ITProduct)))
        self.company = None

        last = {(row['sheet'], row['values']['key']): row['row'] for row in record.rows if row['values']['key']}
        rows = []
        for row in record.rows:
            values = row['values']
            entry = {'sheet': row['sheet'], 'row_number': row['row'], 'key': values['key'], 'action': None,
                     'errors': [], 'warnings': []}
            errors = self._errors(row['sheet'], values)
            if errors:
                entry.update(status='error', errors=errors)
            elif last[(row['sheet'], values['key'])] != row['row']:
                entry.update(status='skipped', warnings=['Идентификатор повторяется ниже на листе; применяется последняя строка'])
            else:
                handler = {'Вузы': self._university, 'Направления': self._direction, 'Продукты РТК': self._product}[row['sheet']]
                handler(values, entry)
            rows.append(entry)
        if self.apply:
            db.flush()
        report = _report(rows, self.created, self.updated)
        report['unmatched_universities'] = self.unmatched
        report['sheets'] = record.sheets
        return report

    @staticmethod
    def _errors(sheet, values):
        spec = SUPPORTED_SHEETS[sheet]
        errors = []
        if not values['key']:
            errors.append(f'Нет идентификатора «{spec.key}»')
        elif len(values['key']) > 64:
            errors.append(f'Идентификатор «{spec.key}» длиннее 64 символов')
        required = 'full_name' if sheet == 'Вузы' else 'name'
        if not values[required]:
            errors.append(f'Нет значения «{spec.columns[required]}»')
        for name, max_length in spec.max_lengths.items():
            if len(values[name]) > max_length:
                errors.append(f'«{spec.columns[name]}» длиннее {max_length} символов')
        return errors

    def _set(self, target, changes, entry, kind):
        # Returns True when something differs; writes only on apply.
        changed = {name: value for name, value in changes.items() if getattr(target, name) != value}
        if changed:
            entry['action'] = 'update'
            self.updated[kind] += 1
            if self.apply:
                for name, value in changed.items():
                    setattr(target, name, value)
        else:
            entry['action'] = 'unchanged'
        entry['status'] = 'ok'

    def _university(self, values, entry):
        university = self.university_by_id.get(values['key'])
        if university is None:
            university = (self.university_by_name.get(name_key(values['full_name']))
                          or (self.university_by_name.get(name_key(values['short_name'])) if values['short_name'] else None))
            if university is not None and university.external_id and university.external_id != values['key']:
                entry.update(status='error', errors=[f'Вуз «{university.name}» уже связан с идентификатором {university.external_id}'])
                return
        if university is None:
            self.unmatched.append({'external_id': values['key'], 'name': values['full_name'], 'short_name': values['short_name']})
            entry.update(status='skipped', warnings=[f'Вуз «{values["full_name"]}» не найден в каталоге CRM; строка пропущена, вуз не создан'])
            return
        entry['name'] = university.name
        # The university keeps its CRM name; the workbook fills the descriptive fields.
        changes = {'external_id': values['key'], 'region': values['region'], 'city': values['city'], 'website': values['website']}
        if values['short_name']:
            changes['short_name'] = values['short_name']
        self._set(university, changes, entry, 'universities')
        self.university_by_id[values['key']] = university

    def _direction(self, values, entry):
        direction = next((d for d in self.directions if d.external_id == values['key']), None) or next(
            (d for d in self.directions if not d.external_id and name_key(d.name) == name_key(values['name'])), None)
        clash = next((d for d in self.directions if d is not direction and name_key(d.name) == name_key(values['name'])), None)
        if clash is not None:
            entry.update(status='error', errors=[f'ИТ-направление «{values["name"]}» уже есть с другим идентификатором'])
            return
        if direction is None:
            entry.update(action='create', status='ok')
            self.created['it_directions'] += 1
            direction = ITDirection(name=values['name'], description=values['description'], external_id=values['key'])
            self.directions.append(direction)
            if self.apply:
                self.db.add(direction)
            return
        self._set(direction, {'external_id': values['key'], 'name': values['name'], 'description': values['description']},
                  entry, 'it_directions')

    def _product(self, values, entry):
        product = next((p for p in self.products if p.external_id == values['key']), None) or next(
            (p for p in self.products if not p.external_id and name_key(p.vendor) == name_key(RTK_VENDOR)
             and name_key(p.name) == name_key(values['name'])), None)
        clash = next((p for p in self.products if p is not product and name_key(p.vendor) == name_key(RTK_VENDOR)
                      and name_key(p.name) == name_key(values['name'])), None)
        if clash is not None:
            entry.update(status='error', errors=[f'ИТ-продукт «{values["name"]}» уже есть с другим идентификатором'])
            return
        if product is None:
            entry.update(action='create', status='ok')
            self.created['it_products'] += 1
            product = ITProduct(vendor=RTK_VENDOR, name=values['name'], description=values['description'], external_id=values['key'])
            self.products.append(product)
            if self.apply:
                product.company = self._company()
                self.db.add(product)
            return
        self._set(product, {'external_id': values['key'], 'name': values['name'], 'description': values['description']},
                  entry, 'it_products')
        if self.apply and product.company_id is None:
            product.company = self._company()

    def _company(self):
        if self.company is None:
            self.company = self.db.scalar(select(VendorCompany).where(VendorCompany.name == RTK_VENDOR))
            if self.company is None:
                self.company = VendorCompany(name=RTK_VENDOR)
                self.db.add(self.company)
        return self.company


def _report(rows, created, updated):
    statuses = [row['status'] for row in rows]
    return {
        'summary': {
            'rows': len(rows),
            'valid': statuses.count('ok'),
            'invalid': statuses.count('error'),
            'skipped': statuses.count('skipped'),
            'with_warnings': sum(1 for row in rows if row['status'] == 'ok' and row['warnings']),
            'created': created,
            'updated': updated,
        },
        'rows': rows,
    }
