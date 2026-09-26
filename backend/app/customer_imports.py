"""In-memory validation and transactional application of customer files.

Reports contain row positions and safe diagnostics, never source cells or document values.
"""
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import select

from .errors import AppError, ErrorCode
from .importer import ImportFileError, MAX_DATA_ROWS, MAX_FILE_BYTES, normalize_header, parse_date, read_upload
from .learner_routes import LearnerIn, apply_fields
from .models import CourseApplication, ITProduct, Learner, VendorCompany, VendorContact

VENDOR_COLUMNS = {
    'компания': 'company', 'продукт': 'products', 'фио': 'full_name',
    'телефон': 'phone', 'почта': 'email', 'способ связи': 'channels',
}
LEARNER_COLUMNS = {
    'фамилия': 'last_name', 'имя': 'first_name', 'отчество': 'middle_name',
    'телефон': 'phone', 'email': 'email', 'почта': 'email', 'электронная почта': 'email',
    'снилс': 'snils', 'серия паспорта': 'passport_series', 'номер паспорта': 'passport_number',
    'кем выдан': 'passport_issued_by', 'кем выдан паспорт': 'passport_issued_by',
    'когда выдан': 'passport_issued_at', 'дата выдачи паспорта': 'passport_issued_at',
    'код подразделения': 'passport_department_code', 'пол': 'gender', 'дата рождения': 'birth_date',
    'регион': 'registration_region', 'регион регистрации': 'registration_region',
    'населенный пункт': 'registration_locality', 'улица': 'registration_street',
    'дом': 'registration_house', 'квартира': 'registration_apartment',
    'индекс': 'postal_code', 'индекс регистрации': 'postal_code',
    'имя в дательном падеже': 'dative_first_name',
    'фамилия в дательном падеже': 'dative_last_name',
    'отчество в дательном падеже': 'dative_middle_name',
    'образование': 'education', 'профессия по диплому': 'diploma_profession',
    'учебное заведение': 'diploma_institution', 'фамилия в дипломе': 'diploma_last_name',
    'номер диплома': 'diploma_number', 'серия диплома': 'diploma_series',
    'регистрационный номер диплома': 'diploma_registration_number',
    'дата выдачи диплома': 'diploma_issued_at',
}
LEARNER_TEMPLATE_HEADERS = (
    'Фамилия', 'Имя', 'Отчествопри наличии)', 'Номер телефона', 'Email', 'СНИЛС',
    'Серия паспорта', 'Номер паспорта', 'Кем выдан паспорт', 'Дата выдачи паспорта',
    'Код подразделения', 'Пол', 'Дата рождения', 'Регион регистрации',
    'Населенный пункт регистрации', 'Улица регистрации', 'Дом регистрации',
    'Квартира регистрации', 'Индекс регистрации', 'Имядательный падеж)',
    'Фамилиядательный падеж)', 'Отчестводательный падеж)', 'Образование',
    'Профессия по диплому', 'Учебное заведение по диплому',
    'Фамилия, указанная в дипломе', 'Номер диплома', 'Серия диплома',
    'Регистрационный номер диплома', 'Дата выдачи диплома',
)
VENDOR_TEMPLATE_HEADERS = ('Компания', 'Продукт', 'ФИО', 'Телефон', 'Почта', 'Способ связи')
LEARNER_COLUMNS.update({
    'отчествопри наличии': 'middle_name',
    'номер телефона': 'phone',
    'населенный пункт регистрации': 'registration_locality',
    'улица регистрации': 'registration_street',
    'дом регистрации': 'registration_house',
    'квартира регистрации': 'registration_apartment',
    'имядательный падеж': 'dative_first_name',
    'фамилиядательный падеж': 'dative_last_name',
    'отчестводательный падеж': 'dative_middle_name',
    'учебное заведение по диплому': 'diploma_institution',
    'фамилия указанная в дипломе': 'diploma_last_name',
})
APPLICATION_COLUMNS = {
    'Номер заявки': 'external_number', 'Курс': 'course', 'Фамилия': 'last_name',
    'Имя': 'first_name', 'Отчество': 'middle_name', 'Телефон': 'phone',
    'Email': 'email', 'Номер потока': 'stream_number',
}
DOCUMENT_FIELDS = {
    'snils', 'passport_series', 'passport_number', 'passport_department_code',
    'diploma_number', 'diploma_series', 'diploma_registration_number', 'postal_code',
}


@dataclass
class CustomerFile:
    kind: str
    template_version: str
    headers: list[str]
    mapping: dict[str, str]
    unmapped_headers: list[str]
    rows: list[tuple[int, dict | None]]


def key(value):
    return ' '.join(str(value or '').split()).casefold().replace('ё', 'е')


def phone_key(value):
    digits = re.sub(r'\D', '', str(value or ''))
    if len(digits) == 10:
        return '7' + digits
    if len(digits) == 11 and digits.startswith('8'):
        return '7' + digits[1:]
    return digits


def email_key(value):
    return str(value or '').strip().casefold()


def split_list(value):
    return [item.strip() for item in re.split(r'[,;\n]+', str(value or '')) if item.strip()]


def read_rows(kind, filename, content):
    return read_customer_file(kind, filename, content).rows


def read_customer_file(kind, filename, content):
    if len(content) > MAX_FILE_BYTES:
        raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, 'Файл больше 10 МБ')
    if kind == 'applications':
        if not filename.lower().endswith('.json'):
            raise AppError(ErrorCode.UNSUPPORTED_MEDIA_TYPE, 'Для заявок нужен файл JSON')
        try:
            items = json.loads(content.decode('utf-8'))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise AppError(ErrorCode.VALIDATION_ERROR, 'Не удалось прочитать JSON') from error
        if not isinstance(items, list) or len(items) > MAX_DATA_ROWS:
            raise AppError(ErrorCode.VALIDATION_ERROR, 'Ожидается массив не более 5000 записей')
        return CustomerFile(kind, 'customer-applications-v1', list(APPLICATION_COLUMNS),
                            {field: header for header, field in APPLICATION_COLUMNS.items()}, [],
                            [(position, item) for position, item in enumerate(items, 1)])
    try:
        sheet = read_upload(filename, content)
    except ImportFileError as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, str(error)) from error
    columns = VENDOR_COLUMNS if kind == 'vendors' else LEARNER_COLUMNS
    mapping = {}
    by_index = {}
    unknown = []
    for index, header in enumerate(sheet.headers):
        normalized = normalize_header(header)
        if normalized in columns:
            field = columns[normalized]
            if field in mapping:
                raise AppError(ErrorCode.VALIDATION_ERROR, 'Два столбца соответствуют одному полю анкеты')
            mapping[field] = header
            by_index[index] = field
        elif not re.fullmatch(r'Столбец \d+', header):
            unknown.append(header)
    required = {'company', 'products', 'full_name'} if kind == 'vendors' else {'last_name', 'first_name'}
    if not required.issubset(mapping):
        raise AppError(ErrorCode.VALIDATION_ERROR, 'Не найдены обязательные столбцы')
    rows = []
    for number, cells in sheet.rows:
        values = {field: cells[index] for index, field in by_index.items() if index < len(cells)}
        rows.append((number, values))
    template = VENDOR_TEMPLATE_HEADERS if kind == 'vendors' else LEARNER_TEMPLATE_HEADERS
    exact = [normalize_header(header) for header in sheet.headers[:len(template)]] == [normalize_header(header) for header in template]
    version = f'customer-{kind}-v1' if exact else f'customer-{kind}-custom'
    return CustomerFile(kind, version, sheet.headers, mapping, unknown, rows)


class CustomerImportRunner:
    def __init__(self, db, request, *, apply, resolved_learner_ids=None):
        self.db = db
        self.request = request
        self.apply = apply
        self.resolved_learner_ids = resolved_learner_ids or {}
        self.seen_application_numbers = set()
        self.current_row_number = None
        self.companies = {key(row.name): row for row in db.scalars(select(VendorCompany))}
        self.products = {(row.company_id, key(row.name)): row for row in db.scalars(select(ITProduct)) if row.company_id}
        self.contacts = {}
        for row in db.scalars(select(VendorContact)):
            self.contacts.setdefault((row.company_id, key(row.full_name)), []).append(row)
        self.learners = list(db.scalars(select(Learner)))
        self.applications = {row.external_number: row for row in db.scalars(select(CourseApplication))}

    def run(self, kind, rows):
        report = []
        created = updated = 0
        for number, raw in rows:
            self.current_row_number = number
            entry = {'row_number': number, 'status': 'ok', 'action': None, 'errors': [], 'warnings': [], 'candidate_ids': []}
            if raw is None:
                entry.update(status='skipped', warnings=['Значение null пропущено'])
            elif not isinstance(raw, dict):
                entry.update(status='error', errors=['Ожидается объект со значениями полей'])
            else:
                try:
                    if kind == 'vendors':
                        action, count = self.vendor(raw)
                    elif kind == 'learners':
                        action, count = self.learner(raw)
                    else:
                        action, count = self.application(raw)
                    entry['action'] = action
                    if action == 'created':
                        created += count
                    elif action == 'updated':
                        updated += count
                except ImportRowError as error:
                    entry.update(status='error', errors=[str(error)], candidate_ids=error.candidate_ids)
            report.append(entry)
        statuses = [entry['status'] for entry in report]
        return {
            'summary': {'rows': len(report), 'valid': statuses.count('ok'), 'invalid': statuses.count('error'),
                        'skipped': statuses.count('skipped'), 'created': created, 'updated': updated},
            'rows': report,
        }

    def vendor(self, raw):
        if isinstance(raw.get('phone'), (int, float)) and not isinstance(raw.get('phone'), bool):
            raise ImportRowError('Телефон должен быть текстом: ведущие нули могли быть потеряны')
        company_name = str(raw.get('company') or '').strip()
        names = split_list(raw.get('products'))
        full_name = str(raw.get('full_name') or '').strip()
        if not company_name or not names or not full_name:
            raise ImportRowError('Нужны компания, продукт и ФИО контакта')
        if any(len(value) > 200 for value in [company_name, full_name, *names]):
            raise ImportRowError('Название или ФИО длиннее 200 символов')
        channels = list(dict.fromkeys(split_list(raw.get('channels'))))
        phone = str(raw.get('phone') or '').strip()
        email = str(raw.get('email') or '').strip()
        if email and ('@' not in email or email.startswith('@') or email.endswith('@')):
            raise ImportRowError('Некорректный формат почты')
        if len(phone) > 50 or len(email) > 254 or any(len(channel) > 50 for channel in channels):
            raise ImportRowError('Слишком длинное контактное поле')
        company = self.companies.get(key(company_name))
        existing_matches = self.contacts.get((company.id, key(full_name)), []) if company else []
        if len(existing_matches) > 1:
            raise ImportRowError('Неоднозначный контакт компании; требуется ручное разрешение')
        added = 0
        if company is None:
            company = VendorCompany(name=company_name) if self.apply else SimpleNamespace(id=-len(self.companies) - 1, name=company_name)
            if self.apply:
                self.db.add(company)
                self.db.flush()
            self.companies[key(company_name)] = company
            added += 1
        products = []
        for name in dict.fromkeys(names):
            product = self.products.get((company.id, key(name)))
            if product is None:
                product = ITProduct(vendor=company.name, name=name, company=company) if self.apply else SimpleNamespace(id=-len(self.products) - 1, name=name)
                if self.apply:
                    self.db.add(product)
                    self.db.flush()
                self.products[(company.id, key(name))] = product
                added += 1
            products.append(product)
        contact_key = (company.id, key(full_name))
        matches = self.contacts.get(contact_key, [])
        if not matches:
            contact = VendorContact(company=company, full_name=full_name, phone=phone, email=email,
                                    preferred_channels=channels, products=products) if self.apply else SimpleNamespace(id=-len(self.contacts)-1)
            if self.apply:
                self.db.add(contact)
                self.db.flush()
            self.contacts[contact_key] = [contact]
            added += 1
        elif self.apply:
            contact = matches[0]
            if phone:
                contact.phone = phone
            if email:
                contact.email = email
            if channels:
                contact.preferred_channels = list(dict.fromkeys([*contact.preferred_channels, *channels]))
            for product in products:
                if product not in contact.products:
                    contact.products.append(product)
        return ('created', added) if added else ('updated', 1)

    def match_learner(self, phone, email):
        phone, email = phone_key(phone), email_key(email)
        if not phone and not email:
            raise ImportRowError('Нужен телефон или email для сопоставления слушателя')
        matches = [row for row in self.learners if
                   (phone and phone_key(row.phone) == phone) or (email and email_key(row.email) == email)]
        if len(matches) > 1:
            chosen_id = self.resolved_learner_ids.get(str(self.current_row_number))
            selected = next((row for row in matches if row.id == chosen_id), None)
            if selected is not None:
                return selected
            raise ImportRowError('Неоднозначное совпадение слушателей; требуется ручное разрешение',
                                 candidate_ids=[row.id for row in matches if row.id > 0])
        return matches[0] if matches else None

    def learner(self, raw):
        for field in DOCUMENT_FIELDS | {'phone'}:
            value = raw.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                raise ImportRowError('Телефон, документные номера и индекс должны быть текстом: ведущие нули могли быть потеряны')
        submitted = {field: value for field, value in raw.items() if value is not None and str(value).strip()}
        for field in ('passport_issued_at', 'birth_date', 'diploma_issued_at'):
            if field in submitted:
                submitted[field] = parse_date(submitted[field]) or submitted[field]
        try:
            validated = LearnerIn.model_validate(submitted).model_dump(exclude_none=True, exclude_unset=True)
        except ValidationError as error:
            field = '.'.join(str(part) for part in error.errors()[0]['loc'])
            raise ImportRowError(f'Некорректный формат поля «{field}»') from error
        match = self.match_learner(validated.get('phone'), validated.get('email'))
        if match is None:
            if self.apply:
                match = Learner(last_name=validated['last_name'], first_name=validated['first_name'])
                apply_fields(match, validated, self.request)
                self.db.add(match)
                self.db.flush()
            else:
                match = SimpleNamespace(id=-len(self.learners)-1, phone=validated.get('phone'), email=validated.get('email'))
            self.learners.append(match)
            return 'created', 1
        if self.apply:
            apply_fields(match, validated, self.request)
        return 'updated', 1

    def application(self, raw):
        values = {field: raw.get(column) for column, field in APPLICATION_COLUMNS.items()}
        number = str(values.get('external_number') or '').strip()
        course = str(values.get('course') or '').strip()
        stream = str(values.get('stream_number') or '').strip()
        if not number or not course or not stream or not values.get('last_name') or not values.get('first_name'):
            raise ImportRowError('Нужны номер заявки, курс, поток и ФИО слушателя')
        if len(number) > 100 or len(course) > 200 or len(stream) > 100:
            raise ImportRowError('Слишком длинный номер заявки, курс или поток')
        if number in self.seen_application_numbers:
            raise ImportRowError('Номер заявки повторяется в файле')
        email = str(values.get('email') or '').strip()
        if email and ('@' not in email or email.startswith('@') or email.endswith('@')):
            raise ImportRowError('Некорректный формат почты')
        existing = self.applications.get(number)
        if existing is not None:
            if self.apply:
                existing.course = course
                existing.stream_number = stream
            self.seen_application_numbers.add(number)
            return 'updated', 1
        learner = self.match_learner(values.get('phone'), values.get('email'))
        if learner is None:
            values['last_name'] = str(values['last_name']).strip()
            values['first_name'] = str(values['first_name']).strip()
            if self.apply:
                learner = Learner(last_name=values['last_name'], first_name=values['first_name'],
                                  middle_name=str(values.get('middle_name') or '').strip(),
                                  phone=str(values.get('phone') or '').strip(), email=str(values.get('email') or '').strip())
                self.db.add(learner)
                self.db.flush()
            else:
                learner = SimpleNamespace(id=-len(self.learners)-1, phone=values.get('phone'), email=values.get('email'))
            self.learners.append(learner)
        application = CourseApplication(external_number=number, course=course, stream_number=stream,
                                        learner_id=learner.id) if self.apply else SimpleNamespace(external_number=number)
        if self.apply:
            self.db.add(application)
            self.db.flush()
        self.applications[number] = application
        self.seen_application_numbers.add(number)
        return 'created', 1


class ImportRowError(Exception):
    """A safe row diagnostic with no source personal data."""

    def __init__(self, message, *, candidate_ids=()):
        super().__init__(message)
        self.candidate_ids = list(candidate_ids)
