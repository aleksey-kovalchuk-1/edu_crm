"""In-memory validation and transactional application of customer files.

Reports contain row positions and safe diagnostics, never source cells or document values.
"""
import json
import re
from dataclasses import asdict, dataclass
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import select

from .errors import AppError, ErrorCode
from .fraud_rules import FraudSignal, evaluate_application, evaluate_learner_match_conflict, evaluate_shared_contact
from .fraud_fingerprint import preview_document_matches, sync_fingerprints
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
    mapping_conflicts: dict[str, list[str]] | None = None


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


def normalize_import_phone(value):
    if isinstance(value, int) and not isinstance(value, bool):
        digits = str(value)
        if len(digits) == 11 and digits[0] in '78':
            return digits, ['Телефон был числом Excel; проверьте исходную ячейку']
        raise ImportRowError('Телефон должен быть текстом: числовое значение нельзя восстановить без проверки')
    if isinstance(value, float):
        raise ImportRowError('Телефон должен быть текстом: числовое значение нельзя восстановить без проверки')
    return value, []


def read_rows(kind, filename, content):
    return read_customer_file(kind, filename, content).rows


def read_customer_file(kind, filename, content, *, selected_mapping=None):
    if len(content) > MAX_FILE_BYTES:
        raise AppError(ErrorCode.PAYLOAD_TOO_LARGE, 'Файл больше 10 МБ')
    if kind == 'applications':
        if selected_mapping is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, 'Ручное сопоставление для JSON не требуется')
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
        sheet = read_upload(filename, content, allow_empty_rows=True)
    except ImportFileError as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, str(error)) from error
    columns = VENDOR_COLUMNS if kind == 'vendors' else LEARNER_COLUMNS
    mapping = {}
    by_index = {}
    unknown = []
    conflicts = {}
    if selected_mapping is not None:
        if not isinstance(selected_mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in selected_mapping.items()):
            raise AppError(ErrorCode.VALIDATION_ERROR, 'Некорректное сопоставление столбцов')
        if not set(selected_mapping).issubset(set(columns.values())):
            raise AppError(ErrorCode.VALIDATION_ERROR, 'Неизвестное поле анкеты в сопоставлении')
        if len(set(selected_mapping.values())) != len(selected_mapping):
            raise AppError(ErrorCode.VALIDATION_ERROR, 'Один столбец выбран для нескольких полей')
        for field, header in selected_mapping.items():
            indices = [index for index, source in enumerate(sheet.headers) if source == header and not re.fullmatch(r'Столбец \d+', source)]
            if len(indices) != 1:
                raise AppError(ErrorCode.VALIDATION_ERROR, 'Выбранный столбец отсутствует или повторяется')
            mapping[field] = header
            by_index[indices[0]] = field
        unknown = [header for index, header in enumerate(sheet.headers) if index not in by_index and not re.fullmatch(r'Столбец \d+', header)]
    else:
        for index, header in enumerate(sheet.headers):
            normalized = normalize_header(header)
            if normalized in columns:
                field = columns[normalized]
                if field in mapping:
                    conflicts.setdefault(field, [mapping[field]]).append(header)
                    unknown.append(header)
                    continue
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
    return CustomerFile(kind, version, sheet.headers, mapping, unknown, rows, conflicts)


class CustomerImportRunner:
    def __init__(self, db, request, *, apply, resolved_learner_ids=None):
        self.db = db
        self.request = request
        self.apply = apply
        self.resolved_learner_ids = resolved_learner_ids or {}
        self.seen_application_numbers = set()
        self.preview_document_index = {}
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
        record_links = []
        created = updated = 0
        for number, raw in rows:
            self.current_row_number = number
            self.current_match_explicitly_resolved = False
            self.current_entity = None
            self.row_signals = []
            self.row_warnings = []
            entry = {'row_number': number, 'status': 'ok', 'action': None, 'errors': [], 'warnings': [], 'candidate_ids': [], 'signals': []}
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
                    entry['signals'] = [asdict(signal) for signal in self.row_signals]
                    if self.apply and self.current_entity is not None:
                        entity_type, entity_id = self.current_entity
                        record_links.append({'row_number': number, 'entity_type': entity_type,
                                             'entity_id': entity_id, 'action': action})
                    if action == 'created':
                        created += count
                    elif action == 'updated':
                        updated += count
                except ImportRowError as error:
                    entry.update(status='error', errors=[str(error)], candidate_ids=error.candidate_ids,
                                 signals=[asdict(signal) for signal in [*self.row_signals, *error.signals]])
                entry['warnings'].extend(self.row_warnings)
            report.append(entry)
        statuses = [entry['status'] for entry in report]
        return {
            'summary': {'rows': len(report), 'valid': statuses.count('ok'), 'invalid': statuses.count('error'),
                        'skipped': statuses.count('skipped'), 'created': created, 'updated': updated},
            'rows': report,
            'record_links': record_links,
        }

    def vendor(self, raw):
        phone_value, warnings = normalize_import_phone(raw.get('phone'))
        self.row_warnings.extend(warnings)
        company_name = str(raw.get('company') or '').strip()
        names = split_list(raw.get('products'))
        full_name = str(raw.get('full_name') or '').strip()
        if not company_name or not names or not full_name:
            raise ImportRowError('Нужны компания, продукт и ФИО контакта')
        if any(len(value) > 200 for value in [company_name, full_name, *names]):
            raise ImportRowError('Название или ФИО длиннее 200 символов')
        channels = list(dict.fromkeys(split_list(raw.get('channels'))))
        phone = str(phone_value or '').strip()
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
        if self.apply:
            self.current_entity = ('vendor_contact', contact.id)
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
                self.current_match_explicitly_resolved = True
                self.row_signals.extend(evaluate_shared_contact({row.id for row in matches}, selected.id, self.current_row_number))
                return selected
            raise ImportRowError('Неоднозначное совпадение слушателей; требуется ручное разрешение',
                                 candidate_ids=[row.id for row in matches if row.id > 0],
                                 signals=evaluate_learner_match_conflict([row.id for row in matches], self.current_row_number))
        return matches[0] if matches else None

    def learner(self, raw):
        phone_value, warnings = normalize_import_phone(raw.get('phone'))
        self.row_warnings.extend(warnings)
        raw = {**raw, 'phone': phone_value}
        for field in DOCUMENT_FIELDS:
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
        shared_ids = {row.id for row in self.learners if
                      (validated.get('phone') and phone_key(row.phone) == phone_key(validated['phone'])) or
                      (validated.get('email') and email_key(row.email) == email_key(validated['email']))}
        if match is not None and (key(match.last_name) != key(validated['last_name']) or
                                  key(match.first_name) != key(validated['first_name'])):
            match = None
        if match is None:
            if self.apply:
                match = Learner(last_name=validated['last_name'], first_name=validated['first_name'])
                apply_fields(match, validated, self.request)
                self.db.add(match)
                self.db.flush()
                self.row_signals.extend(sync_fingerprints(self.db, match, self.request))
            else:
                match = SimpleNamespace(id=-len(self.learners)-1, phone=validated.get('phone'), email=validated.get('email'),
                                        last_name=validated['last_name'], first_name=validated['first_name'])
            self.learners.append(match)
            if not self.apply:
                self.row_signals.extend(preview_document_matches(
                    self.db, validated, self.request, incoming_learner_id=match.id,
                    row_number=self.current_row_number, in_file_index=self.preview_document_index))
            if shared_ids:
                self.row_warnings.append('Контакт уже встречается у другой анкеты; проверьте совпадение')
                self.row_signals.extend(evaluate_shared_contact(shared_ids, match.id, self.current_row_number))
            if self.apply:
                self.current_entity = ('learner', match.id)
            return 'created', 1
        if self.apply:
            apply_fields(match, validated, self.request)
            self.current_entity = ('learner', match.id)
            self.row_signals.extend(sync_fingerprints(self.db, match, self.request))
        else:
            self.row_signals.extend(preview_document_matches(
                self.db, validated, self.request, learner=match if isinstance(match, Learner) else None,
                incoming_learner_id=match.id, row_number=self.current_row_number,
                in_file_index=self.preview_document_index))
        shared_signals = evaluate_shared_contact(shared_ids, match.id, self.current_row_number)
        if shared_signals:
            self.row_warnings.append('Контакт уже встречается у другой анкеты; проверьте совпадение')
            self.row_signals.extend(shared_signals)
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
            raise ImportRowError('Номер заявки повторяется в файле', signals=[
                FraudSignal('batch_repetition', 1, 'medium', None, None, None, self.current_row_number)])
        email = str(values.get('email') or '').strip()
        if email and ('@' not in email or email.startswith('@') or email.endswith('@')):
            raise ImportRowError('Некорректный формат почты')
        existing = self.applications.get(number)
        if existing is not None:
            proposed = self.match_learner(values.get('phone'), values.get('email'))
            same_name = existing.learner is not None and (key(existing.learner.last_name) == key(values['last_name']) and
                         key(existing.learner.first_name) == key(values['first_name']))
            signals = evaluate_application(existing, proposed.id if proposed is not None and same_name else None,
                                           course, stream, self.current_row_number)
            if signals:
                raise ImportRowError('Номер заявки противоречит сохранённой карточке; требуется проверка', signals=signals)
            self.seen_application_numbers.add(number)
            if self.apply:
                self.current_entity = ('course_application', existing.id)
            return 'updated', 1
        learner = self.match_learner(values.get('phone'), values.get('email'))
        shared_ids = {row.id for row in self.learners if
                      (values.get('phone') and phone_key(row.phone) == phone_key(values['phone'])) or
                      (values.get('email') and email_key(row.email) == email_key(values['email']))}
        explicitly_resolved = self.current_match_explicitly_resolved
        if learner is not None and not explicitly_resolved and (
                key(learner.last_name) != key(values['last_name']) or
                key(learner.first_name) != key(values['first_name'])):
            learner = None
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
                learner = SimpleNamespace(id=-len(self.learners)-1, phone=values.get('phone'), email=values.get('email'),
                                          last_name=values['last_name'], first_name=values['first_name'])
            self.learners.append(learner)
            shared_signals = evaluate_shared_contact(shared_ids, learner.id, self.current_row_number)
            if shared_signals:
                self.row_warnings.append('Контакт уже встречается у другой анкеты; проверьте совпадение')
                self.row_signals.extend(shared_signals)
        application = CourseApplication(external_number=number, course=course, stream_number=stream,
                                        learner_id=learner.id) if self.apply else SimpleNamespace(external_number=number)
        if self.apply:
            self.db.add(application)
            self.db.flush()
        self.applications[number] = application
        self.seen_application_numbers.add(number)
        if self.apply:
            self.current_entity = ('course_application', application.id)
        return 'created', 1


class ImportRowError(Exception):
    """A safe row diagnostic with no source personal data."""

    def __init__(self, message, *, candidate_ids=(), signals=()):
        super().__init__(message)
        self.candidate_ids = list(candidate_ids)
        self.signals = list(signals)
