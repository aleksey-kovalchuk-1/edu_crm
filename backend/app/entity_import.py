"""Generic entity-import registry (T-091/T-092, `docs/design/file-ingestion-plan.md` §3.1/§3.2, D-157).

The existing contract importer (`app/importer.py`, `CatalogWriter` in `app/import_routes.py`) is the
working T-033 implementation and is deliberately left untouched: this module adds three more importable
entities -- `universities`, `university_contacts`, `interactions` -- behind the same `CatalogImport`
upload/check/apply lifecycle, dispatched by an `entity` value stored on the upload.

Design notes (see the report handed to the reviewer for the full rationale):

* `CatalogImport` has no `entity` column (adding one needs an Alembic migration, which is out of this
  agent's scope -- migrations belong to a parallel workstream). The entity is instead stored as a reserved
  key inside the existing `suggested_mapping` JSONB column (`ENTITY_KEY`), set once at upload and never
  overwritten afterwards. `decode_entity`/`encode_suggested_mapping` are the only places that know this.
* Apply always runs as one job, one transaction, all-or-nothing -- matching the brief and the existing
  contract importer's behaviour. A validation error on any row still lets the *other* rows apply (an error
  row is simply not written, exactly like the contract importer's `CatalogWriter`); "all-or-nothing" here
  means the whole apply is one DB transaction (a crash mid-way rolls everything back), not that one bad row
  blocks the rest.
* Rollback data (per-row `entity`/`record_id`/`was_new`/`before` snapshot/audit watermark) is carried in the
  job's own `result` dict and mirrored into `CatalogImport.report['rollback']` -- both are existing JSONB
  columns, so again no migration is needed.
"""
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select

from .audit import record_event
from .catalog_routes import managed_university_ids, sees_all
from .importer import RowResult, name_key, normalize_header, normalize_name
from .models import AuditEvent, Launch, StageEvent, StatusChange, University, UniversityContact
from .workflows import active_statuses, default_template

ENTITY_KEY = '__entity__'
ENTITIES = ('universities', 'university_contacts', 'interactions')

# entity -> the entity_type string used elsewhere in the audit trail for its records (catalog_routes.py,
# main.py) -- kept distinct from the plural registry key so rollback's audit-watermark lookups match the
# events that university.create/university_contact.create/launch.create already write.
AUDIT_ENTITY_TYPE = {'universities': 'university', 'university_contacts': 'university_contact', 'interactions': 'launch'}


def _is_empty(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return normalize_name(value) if not _is_empty(value) else ''


def _website(value):
    value = _text(value)
    if value and not value.lower().startswith(('http://', 'https://')):
        return value, 'Адрес сайта должен начинаться с http:// или https://'
    return value, None


def _email(value):
    value = _text(value)
    if value and ('@' not in value or value.startswith('@') or value.endswith('@')):
        return value, 'Некорректный адрес электронной почты'
    return value, None


# ---------- mapping (generalised from importer.suggest_mapping/validate_mapping, parametrised by entity) ----------

def suggest_mapping(fields, headers):
    mapping, used = {}, set()
    for field_name, (_, _, synonyms) in fields.items():
        match = next((header for header in headers if header not in used and normalize_header(header) in synonyms), None)
        mapping[field_name] = match
        if match is not None:
            used.add(match)
    return mapping


def validate_mapping(fields, labels, headers, mapping):
    problems = []
    unknown_fields = sorted(set(mapping) - set(fields))
    if unknown_fields:
        problems.append(f'Неизвестные поля: {", ".join(unknown_fields)}')
    for field_name, (required, _, _) in fields.items():
        if required and not mapping.get(field_name):
            problems.append(f'Не выбран столбец для поля «{labels[field_name]}»')
    chosen = [header for header in mapping.values() if header]
    missing_headers = sorted({header for header in chosen if header not in headers})
    if missing_headers:
        problems.append(f'В файле нет столбцов: {", ".join(missing_headers)}')
    duplicates = sorted({header for header in chosen if chosen.count(header) > 1})
    if duplicates:
        problems.append(f'Один столбец выбран для нескольких полей: {", ".join(duplicates)}')
    return problems


def encode_suggested_mapping(entity, mapping):
    return {**mapping, ENTITY_KEY: entity}


def decode_entity(record):
    """Every `CatalogImport` predating this feature (and every contract upload since -- that endpoint is
    untouched) has no sentinel key, so it is treated as `'contracts'`."""
    return (record.suggested_mapping or {}).get(ENTITY_KEY, 'contracts')


def public_mapping(mapping_dict):
    return {key: value for key, value in (mapping_dict or {}).items() if key != ENTITY_KEY}


# ---------- field tables ----------

UNIVERSITY_FIELDS = {
    'name': (True, 200, ['наименование вуза', 'вуз', 'учебное заведение', 'наименование учебного заведения', 'name', 'university name', 'university']),
    'city': (True, 100, ['город', 'city']),
    'short_name': (False, 100, ['краткое название', 'сокращение', 'short name']),
    'region': (False, 100, ['регион', 'region']),
    'website': (False, 300, ['сайт', 'веб сайт', 'website']),
    'contact': (False, 200, ['контакт', 'контактное лицо', 'contact']),
}
UNIVERSITY_LABELS = {
    'name': 'Наименование вуза', 'city': 'Город', 'short_name': 'Краткое название',
    'region': 'Регион', 'website': 'Сайт', 'contact': 'Контакт',
}

CONTACT_FIELDS = {
    'university_name': (True, 200, ['наименование вуза', 'вуз', 'учебное заведение', 'university', 'university name']),
    'full_name': (True, 200, ['фио', 'ф и о', 'полное имя', 'full name', 'name']),
    'position': (False, 200, ['должность', 'position']),
    'email': (False, 254, ['email', 'e mail', 'эл почта', 'почта']),
    'phone': (False, 50, ['телефон', 'phone']),
    'comment': (False, 2000, ['комментарий', 'примечание', 'comment']),
}
CONTACT_LABELS = {
    'university_name': 'Наименование вуза', 'full_name': 'ФИО', 'position': 'Должность',
    'email': 'Email', 'phone': 'Телефон', 'comment': 'Комментарий',
}

LAUNCH_FIELDS = {
    'university_name': (True, 200, ['наименование вуза', 'вуз', 'учебное заведение', 'university', 'university name']),
    'program': (True, 200, ['программа', 'направление обучения', 'program']),
    'product': (True, 200, ['продукт', 'ит продукт', 'product']),
    'owner': (True, 100, ['ответственный', 'менеджер', 'owner']),
    'students': (False, None, ['студенты', 'число студентов', 'количество студентов', 'students']),
    'deadline': (True, None, ['срок', 'дедлайн', 'срок реализации', 'deadline']),
}
LAUNCH_LABELS = {
    'university_name': 'Наименование вуза', 'program': 'Программа', 'product': 'Продукт',
    'owner': 'Ответственный', 'students': 'Число студентов', 'deadline': 'Срок',
}

FIELDS_BY_ENTITY = {'universities': UNIVERSITY_FIELDS, 'university_contacts': CONTACT_FIELDS, 'interactions': LAUNCH_FIELDS}
LABELS_BY_ENTITY = {'universities': UNIVERSITY_LABELS, 'university_contacts': CONTACT_LABELS, 'interactions': LAUNCH_LABELS}
# Role required to import each entity: 'editor' matches catalog_routes.catalog_editor (supervisor/admin,
# same as creating a university through the API, D-128); 'any' matches the existing any-role creation
# endpoints for contacts/launches, scoped per-row to the importing user's assigned universities.
ROLE_BY_ENTITY = {'universities': 'editor', 'university_contacts': 'any', 'interactions': 'any', 'contracts': 'editor'}


def parse_date(value):
    from .importer import parse_date as _parse_date
    return _parse_date(value)


def from_json_cell(value):
    """Undoes `import_routes._to_json`'s date tagging so a stored cell round-trips back to a `date`."""
    if isinstance(value, dict) and '$date' in value:
        from datetime import date
        return date.fromisoformat(value['$date'])
    return value


def build_rows(headers, stored_rows, mapping):
    """`stored_rows` is `CatalogImport.rows` (`[[row_number, [cell, ...]], ...]`); returns
    `[(row_number, {field: raw_value}), ...]` using the chosen header position for each mapped field."""
    positions = {field_name: headers.index(header) for field_name, header in mapping.items() if header and header in headers}
    rows = []
    for number, cells in stored_rows:
        rows.append((number, {field_name: from_json_cell(cells[position]) if position < len(cells) else None for field_name, position in positions.items()}))
    return rows


# ---------- row parsing ----------

def _parse_common(row_number, raw, fields, labels, skip=()):
    result = RowResult(row_number=row_number)
    for field_name, (required, max_length, _) in fields.items():
        if field_name in skip:
            continue
        text = _text(raw.get(field_name))
        if required and not text:
            result.errors.append(f'Не заполнено поле «{labels[field_name]}»')
        if max_length and len(text) > max_length:
            result.errors.append(f'Поле «{labels[field_name]}» длиннее {max_length} символов')
        result.values[field_name] = text
    return result


def parse_university_row(row_number, raw):
    result = _parse_common(row_number, raw, UNIVERSITY_FIELDS, UNIVERSITY_LABELS)
    website, problem = _website(result.values.get('website'))
    result.values['website'] = website
    if problem:
        result.errors.append(problem)
    return result


def parse_contact_row(row_number, raw):
    result = _parse_common(row_number, raw, CONTACT_FIELDS, CONTACT_LABELS)
    email, problem = _email(result.values.get('email'))
    result.values['email'] = email
    if problem:
        result.errors.append(problem)
    return result


def parse_launch_row(row_number, raw):
    result = _parse_common(row_number, raw, LAUNCH_FIELDS, LAUNCH_LABELS, skip=('students', 'deadline'))

    raw_students = raw.get('students')
    if _is_empty(raw_students):
        result.values['students'] = 0
    else:
        try:
            students = int(float(raw_students)) if not isinstance(raw_students, str) else int(_text(raw_students))
            if students < 0 or students > 100000:
                raise ValueError
            result.values['students'] = students
        except (TypeError, ValueError):
            result.errors.append(f'Число студентов указано неверно: «{_text(raw_students)}»')
            result.values['students'] = None

    raw_deadline = raw.get('deadline')
    deadline = parse_date(raw_deadline)
    if _is_empty(raw_deadline):
        result.errors.append(f'Не заполнено поле «{LAUNCH_LABELS["deadline"]}»')
    elif deadline is None:
        result.errors.append(f'Не удалось распознать срок: «{_text(raw_deadline)}»')
    result.values['deadline'] = deadline
    return result


PARSE_ROW = {'universities': parse_university_row, 'university_contacts': parse_contact_row, 'interactions': parse_launch_row}


def row_identity(entity, values):
    """The in-file duplicate/identity key for a row; the last occurrence of a repeated key wins and earlier
    ones are reported `skipped`, mirroring the contract importer's repeated-contract-number handling."""
    if entity == 'universities':
        return name_key(values['name']) if values.get('name') else None
    if entity == 'university_contacts':
        if not values.get('university_name') or not values.get('full_name'):
            return None
        return (name_key(values['university_name']), name_key(values['full_name']))
    if entity == 'interactions':
        if not values.get('university_name') or not values.get('program'):
            return None
        return (name_key(values['university_name']), name_key(values['program']), values.get('owner'), values.get('deadline'))
    return None


# ---------- write context ----------

@dataclass
class Context:
    db: object
    user: object
    correlation_id: str | None
    universities: dict = field(default_factory=dict)
    contacts: dict = field(default_factory=dict)
    managed_ids: set | None = None
    sees_all: bool = False
    created: int = 0
    updated: int = 0
    rollback: list = field(default_factory=list)


def load_context(db, user, correlation_id):
    ctx = Context(db=db, user=user, correlation_id=correlation_id)
    ctx.universities = {name_key(u.name): u for u in db.scalars(select(University))}
    ctx.contacts = {(c.university_id, name_key(c.full_name)): c for c in db.scalars(select(UniversityContact))}
    ctx.sees_all = sees_all(user)
    ctx.managed_ids = None if ctx.sees_all else set(db.scalars(managed_university_ids(user)))
    return ctx


def _university_for_row(ctx, result, values, *, require_active, require_scope):
    name = values.get('university_name') or values.get('name')
    key = name_key(name)
    university = ctx.universities.get(key)
    if university is None:
        result.errors.append(f'Учебное заведение «{name}» не найдено в CRM')
        return None
    if require_active and not university.is_active:
        result.errors.append(f'Учебное заведение «{name}» неактивно')
        return None
    if require_scope and not ctx.sees_all and university.id not in ctx.managed_ids:
        result.errors.append(f'Учебное заведение «{name}» вам не назначено')
        return None
    return university


def _record_and_watermark(ctx, action, *, entity_type, entity_id, summary, payload):
    event = record_event(ctx.db, None, ctx.user, action, entity_type=entity_type, entity_id=entity_id,
                          summary=summary, payload=payload, correlation_id=ctx.correlation_id)
    ctx.db.flush()
    return event.id


# ---------- per-entity write ----------

def write_university(ctx, result, *, apply):
    values = result.values
    key = name_key(values['name'])
    existing = ctx.universities.get(key)
    if existing is None:
        ctx.created += 1
        if not apply:
            return 'create'
        db = ctx.db
        university = University(name=values['name'], city=values['city'], short_name=values['short_name'],
                                 region=values['region'], website=values['website'], contact=values['contact'])
        db.add(university)
        db.flush()
        ctx.universities[key] = university
        watermark = _record_and_watermark(
            ctx, 'university.create', entity_type='university', entity_id=university.id,
            summary=f'Добавлено учебное заведение «{university.name}» (импорт)',
            payload={'name': university.name, 'city': university.city},
        )
        ctx.rollback.append({'entity': 'universities', 'record_id': university.id, 'was_new': True, 'before': None, 'audit_watermark': watermark})
        return 'create'

    ctx.updated += 1
    if not apply:
        return 'update'
    before, changes = {}, {}
    for field_name in ('city', 'short_name', 'region', 'website', 'contact'):
        new_value = values[field_name]
        if new_value and new_value != getattr(existing, field_name):
            changes[field_name] = new_value
    for field_name, value in changes.items():
        before[field_name] = getattr(existing, field_name)
        setattr(existing, field_name, value)
    if changes:
        watermark = _record_and_watermark(
            ctx, 'university.update', entity_type='university', entity_id=existing.id,
            summary=f'Изменено учебное заведение «{existing.name}» (импорт)', payload=changes,
        )
        ctx.rollback.append({'entity': 'universities', 'record_id': existing.id, 'was_new': False, 'before': before, 'audit_watermark': watermark})
    return 'update'


def write_contact(ctx, result, *, apply):
    values = result.values
    university = _university_for_row(ctx, result, values, require_active=False, require_scope=True)
    if university is None:
        return None
    key = (university.id, name_key(values['full_name']))
    existing = ctx.contacts.get(key)
    if existing is None:
        ctx.created += 1
        if not apply:
            return 'create'
        db = ctx.db
        contact = UniversityContact(university_id=university.id, full_name=values['full_name'], position=values['position'],
                                     email=values['email'], phone=values['phone'], comment=values['comment'])
        db.add(contact)
        db.flush()
        ctx.contacts[key] = contact
        watermark = _record_and_watermark(
            ctx, 'university_contact.create', entity_type='university_contact', entity_id=contact.id,
            summary=f'Добавлен ответственный от вуза «{university.name}» (импорт)', payload={'university_id': university.id},
        )
        ctx.rollback.append({'entity': 'university_contacts', 'record_id': contact.id, 'was_new': True, 'before': None, 'audit_watermark': watermark})
        return 'create'

    ctx.updated += 1
    if not apply:
        return 'update'
    before, changes = {}, {}
    for field_name in ('position', 'email', 'phone', 'comment'):
        new_value = values[field_name]
        if new_value and new_value != getattr(existing, field_name):
            changes[field_name] = new_value
    for field_name, value in changes.items():
        before[field_name] = getattr(existing, field_name)
        setattr(existing, field_name, value)
    if changes:
        watermark = _record_and_watermark(
            ctx, 'university_contact.update', entity_type='university_contact', entity_id=existing.id,
            summary=f'Изменены данные ответственного от вуза «{university.name}» (импорт)', payload={'fields': sorted(changes)},
        )
        ctx.rollback.append({'entity': 'university_contacts', 'record_id': existing.id, 'was_new': False, 'before': before, 'audit_watermark': watermark})
    return 'update'


def write_launch(ctx, result, *, apply):
    values = result.values
    university = _university_for_row(ctx, result, values, require_active=True, require_scope=True)
    if university is None:
        return None
    ctx.created += 1
    if not apply:
        return 'create'
    db = ctx.db
    template = default_template(db)
    first_status = active_statuses(db, template.id)[0]
    launch = Launch(university_id=university.id, program=values['program'], product=values['product'], owner=values['owner'],
                     students=values['students'], deadline=values['deadline'], stage=first_status.position,
                     workflow_template_id=template.id, status_id=first_status.id)
    db.add(launch)
    db.flush()
    db.add(StageEvent(launch_id=launch.id, stage=first_status.position))
    db.add(StatusChange(launch_id=launch.id, from_status_id=None, to_status_id=first_status.id, user_id=ctx.user.id if ctx.user else None))
    watermark = _record_and_watermark(
        ctx, 'launch.create', entity_type='launch', entity_id=launch.id,
        summary=f'Создано взаимодействие «{launch.program}» с «{university.name}» (импорт)',
        payload={'university_id': university.id, 'program': launch.program, 'product': launch.product, 'stage': first_status.position},
    )
    ctx.rollback.append({'entity': 'interactions', 'record_id': launch.id, 'was_new': True, 'before': None, 'audit_watermark': watermark})
    return 'create'


WRITE_ROW = {'universities': write_university, 'university_contacts': write_contact, 'interactions': write_launch}


# ---------- orchestration (mirrors CatalogWriter.run in import_routes.py) ----------

def run_import(db, user, entity, headers, mapping, rows, *, apply, correlation_id=None):
    """`rows` is `[(row_number, {field: raw_value}), ...]`; returns the same `{summary, rows}` report shape
    as the contract importer, plus a `rollback` list (only meaningful when `apply=True`)."""
    fields = FIELDS_BY_ENTITY[entity]
    parse_row = PARSE_ROW[entity]
    write_row = WRITE_ROW[entity]

    results = [parse_row(number, raw) for number, raw in rows]

    last_row = {}
    for result in results:
        if result.is_valid:
            key = row_identity(entity, result.values)
            if key is not None:
                last_row[key] = result.row_number

    ctx = load_context(db, user, correlation_id)
    entries = []
    for result in results:
        entry = {'row_number': result.row_number, 'action': None}
        identity_summary = result.values.get('name') or result.values.get('full_name') or result.values.get('program') or ''
        entry['identity'] = identity_summary
        if not result.is_valid:
            entry.update(status='error', errors=result.errors, warnings=result.warnings)
            entries.append(entry)
            continue
        key = row_identity(entity, result.values)
        if key is not None and last_row.get(key) != result.row_number:
            entry.update(status='skipped', errors=[], warnings=['Строка повторяется ниже в файле; применяется последняя строка'])
            entries.append(entry)
            continue
        action = write_row(ctx, result, apply=apply)
        if action is None:
            # A per-row reference/scope problem surfaced through result.errors inside write_row.
            entry.update(status='error', errors=result.errors, warnings=result.warnings)
        else:
            entry['action'] = action
            entry.update(status='warning' if result.warnings else 'ok', errors=[], warnings=result.warnings)
        entries.append(entry)

    statuses = [entry['status'] for entry in entries]
    report = {
        'summary': {
            'rows': len(entries),
            'valid': statuses.count('ok') + statuses.count('warning'),
            'invalid': statuses.count('error'),
            'skipped': statuses.count('skipped'),
            'with_warnings': statuses.count('warning'),
            'created': {entity: ctx.created},
            'updated': {entity: ctx.updated},
        },
        'rows': entries,
    }
    if apply:
        report['rollback'] = ctx.rollback
    return report


# ---------- rollback ----------

UNDO_MODEL = {'universities': University, 'university_contacts': UniversityContact}


def _has_later_change(db, entity, record_id, watermark):
    audit_type = AUDIT_ENTITY_TYPE[entity]
    return db.scalar(
        select(func.count()).select_from(AuditEvent)
        .where(AuditEvent.entity_type == audit_type, AuditEvent.entity_id == str(record_id), AuditEvent.id > watermark)
    ) > 0


def rollback_import(db, rollback_entries):
    """Undoes what `run_import(..., apply=True)` recorded, skipping any row changed since (the "safe"
    rollback of `docs/design/file-ingestion-plan.md` §3.2). Returns a per-row outcome list.

    Each row is its own commit: a partial rollback is expected (the plan explicitly rejects making this
    all-or-nothing), so one row's failure (e.g. a later record now references it) must not undo the rows
    already rolled back earlier in the same batch.
    """
    items = []
    for entry in rollback_entries:
        entity, record_id, was_new = entry['entity'], entry['record_id'], entry['was_new']
        watermark = entry.get('audit_watermark')
        if watermark is not None and _has_later_change(db, entity, record_id, watermark):
            items.append({'entity': entity, 'record_id': record_id, 'status': 'not_rolled_back', 'reason': 'Запись изменена после импорта'})
            continue
        try:
            if was_new:
                _undo_created(db, entity, record_id)
            else:
                _undo_updated(db, entity, record_id, entry.get('before') or {})
            db.commit()
        except Exception:  # noqa: BLE001 - an FK conflict (e.g. a contact added later) must not abort the batch
            db.rollback()
            items.append({'entity': entity, 'record_id': record_id, 'status': 'not_rolled_back', 'reason': 'Запись используется в других данных'})
            continue
        items.append({'entity': entity, 'record_id': record_id, 'status': 'rolled_back', 'reason': None})
    return items


def _undo_created(db, entity, record_id):
    if entity == 'interactions':
        db.execute(delete(StatusChange).where(StatusChange.launch_id == record_id))
        db.execute(delete(StageEvent).where(StageEvent.launch_id == record_id))
        obj = db.get(Launch, record_id)
    else:
        obj = db.get(UNDO_MODEL[entity], record_id)
    if obj is not None:
        db.delete(obj)


def _undo_updated(db, entity, record_id, before):
    obj = db.get(UNDO_MODEL[entity], record_id)
    if obj is None:
        return
    for field_name, value in before.items():
        setattr(obj, field_name, value)
