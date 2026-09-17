"""Report query, column registry, and file writers (T-050-T-053, D-180-D-183).

Rows are Launches (interactions) -- one row per interaction, matching the required columns
(university, IT direction, IT product, program, interaction/workflow, status, responsible person,
relevant dates). `app/report_jobs.py` runs `build_rows` and one writer inside a background job (D-166);
`app/report_routes.py` only enqueues and serves the finished file.

D-180: `launches.product`/`launches.owner` are free text (no FK to the IT-product or user catalogs --
see `app/models.py`'s `Launch`), so "IT product"/"IT direction"/"responsible person" filters match against
those free-text values rather than catalog ids. The "IT direction"/"IT product" filters resolve the chosen
catalog rows to their `name`s and match `launches.product` against that set (best effort: a product name
shared by two vendors matches both); the "responsible" filter takes the free-text names directly. The
`it_direction` column is populated the same way, so it can be blank when a launch's free-text product has
no catalog counterpart. This is a deliberate, documented limitation of the current schema, not a bug.
"""
import io
import json
import os
from datetime import date

from sqlalchemy import false, func, select

from .catalog_routes import managed_university_ids, sees_all, university_scope
from .models import ITDirection, ITProduct, Launch, University, WorkflowStatus, WorkflowTemplate, StatusChange, it_product_directions

REPORT_COLUMNS = {
    'university': 'Университет',
    'it_direction': 'ИТ-направление',
    'it_product': 'ИТ-продукт',
    'program': 'Программа',
    'workflow': 'Процесс',
    'status': 'Статус',
    'responsible': 'Ответственный',
    'deadline': 'Срок',
    'last_status_change_at': 'Последнее изменение статуса',
}
DEFAULT_COLUMNS = list(REPORT_COLUMNS)
REPORT_FORMATS = ('xlsx', 'xls', 'pdf', 'json')
CONTENT_TYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'xls': 'application/vnd.ms-excel',
    'pdf': 'application/pdf',
    'json': 'application/json',
}


class ReportFilters:
    def __init__(
        self, *, period_from=None, period_to=None, university_ids=None, it_direction_ids=None,
        it_product_ids=None, responsible=None, status_ids=None, columns=None,
    ):
        self.period_from = period_from
        self.period_to = period_to
        self.university_ids = list(university_ids or [])
        self.it_direction_ids = list(it_direction_ids or [])
        self.it_product_ids = list(it_product_ids or [])
        self.responsible = list(responsible or [])
        self.status_ids = list(status_ids or [])
        self.columns = [c for c in (columns or []) if c in REPORT_COLUMNS] or list(DEFAULT_COLUMNS)


def _product_direction_names(db):
    """`{product name (lowercased) -> sorted direction names}`, for the `it_direction` column."""
    rows = db.execute(
        select(ITProduct.name, ITDirection.name)
        .join(it_product_directions, it_product_directions.c.it_product_id == ITProduct.id)
        .join(ITDirection, ITDirection.id == it_product_directions.c.it_direction_id)
    ).all()
    mapping: dict[str, set[str]] = {}
    for product_name, direction_name in rows:
        mapping.setdefault(product_name.strip().lower(), set()).add(direction_name)
    return {key: sorted(names) for key, names in mapping.items()}


def _product_names_for_filters(db, filters):
    """Names to match `launches.product` against, or `None` if neither filter narrows it."""
    if not filters.it_product_ids and not filters.it_direction_ids:
        return None
    names: set[str] = set()
    if filters.it_product_ids:
        names |= set(db.scalars(select(ITProduct.name).where(ITProduct.id.in_(filters.it_product_ids))))
    if filters.it_direction_ids:
        names |= set(db.scalars(
            select(ITProduct.name)
            .join(it_product_directions, it_product_directions.c.it_product_id == ITProduct.id)
            .where(it_product_directions.c.it_direction_id.in_(filters.it_direction_ids))
        ))
    return names


def build_rows(db, user, filters):
    """Report rows for `user`'s data scope (D-141, same as every other CRM endpoint), newest deadline first."""
    last_status_change = (
        select(func.max(StatusChange.created_at))
        .where(StatusChange.launch_id == Launch.id)
        .correlate(Launch)
        .scalar_subquery()
    )
    query = (
        select(
            Launch.id.label('launch_id'), Launch.university_id, University.name.label('university'),
            Launch.product.label('it_product'), Launch.program, WorkflowTemplate.name.label('workflow'),
            WorkflowStatus.id.label('status_id'), WorkflowStatus.name.label('status'),
            Launch.owner.label('responsible'), Launch.deadline, last_status_change.label('last_status_change_at'),
        )
        .join(University, University.id == Launch.university_id)
        .join(WorkflowTemplate, WorkflowTemplate.id == Launch.workflow_template_id)
        .join(WorkflowStatus, WorkflowStatus.id == Launch.status_id)
        .where(university_scope(Launch.university_id, user))
        .order_by(Launch.deadline.desc(), Launch.id)
    )
    if filters.university_ids:
        allowed = set(filters.university_ids)
        if not sees_all(user):
            allowed &= set(db.scalars(managed_university_ids(user)))
        query = query.where(Launch.university_id.in_(allowed) if allowed else false())
    if filters.status_ids:
        query = query.where(WorkflowStatus.id.in_(filters.status_ids))
    if filters.period_from:
        query = query.where(Launch.deadline >= filters.period_from)
    if filters.period_to:
        query = query.where(Launch.deadline <= filters.period_to)
    if filters.responsible:
        query = query.where(Launch.owner.in_(filters.responsible))
    product_names = _product_names_for_filters(db, filters)
    if product_names is not None:
        query = query.where(Launch.product.in_(product_names) if product_names else false())

    direction_map = _product_direction_names(db)
    rows = []
    for row in db.execute(query).mappings():
        directions = direction_map.get(row['it_product'].strip().lower(), ())
        rows.append({
            'launch_id': row['launch_id'],
            'university_id': row['university_id'],
            'status_id': row['status_id'],
            'university': row['university'],
            'it_direction': ', '.join(directions),
            'it_product': row['it_product'],
            'program': row['program'],
            'workflow': row['workflow'],
            'status': row['status'],
            'responsible': row['responsible'],
            'deadline': row['deadline'],
            'last_status_change_at': row['last_status_change_at'],
        })
    return rows


def _cell(row, key):
    value = row[key]
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, 'isoformat'):  # datetime, distinct from date above
        return value.isoformat()
    return value


def to_json_bytes(rows, columns):
    payload = {
        'columns': [{'key': key, 'label': REPORT_COLUMNS[key]} for key in columns],
        'rows': [
            {
                'id': row['launch_id'], 'university_id': row['university_id'], 'status_id': row['status_id'],
                **{key: _cell(row, key) for key in columns},
            }
            for row in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')


def to_xlsx_bytes(rows, columns):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Отчёт'
    sheet.append([REPORT_COLUMNS[key] for key in columns])
    for row in rows:
        sheet.append([_cell(row, key) for key in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def to_xls_bytes(rows, columns):
    import xlwt

    workbook = xlwt.Workbook(encoding='utf-8')
    sheet = workbook.add_sheet('Отчёт')
    for col, key in enumerate(columns):
        sheet.write(0, col, REPORT_COLUMNS[key])
    for row_index, row in enumerate(rows, start=1):
        for col, key in enumerate(columns):
            sheet.write(row_index, col, _cell(row, key))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


FONT_NAME = 'ReportFont'
# In priority order: an explicit override, Docker/CI's apt-installed `fonts-dejavu-core` (see Dockerfile
# and .github/workflows/ci.yml), a Homebrew-installed copy for local dev, then a macOS system font as a
# last resort so PDF export still works untested on a developer's Mac without any of the above.
_FALLBACK_FONT_CANDIDATES = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans.ttf',
    os.path.expanduser('~/Library/Fonts/DejaVuSans.ttf'),
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
)


def _resolve_font_path(settings):
    candidates = ((settings.report_font_path,) if settings and settings.report_font_path else ()) + _FALLBACK_FONT_CANDIDATES
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise RuntimeError(
        'No Cyrillic-capable TTF font found for PDF export. Install fonts-dejavu-core (Docker/CI) or set REPORT_FONT_PATH.'
    )


_font_registered = False


def _ensure_font(settings):
    global _font_registered
    if not _font_registered:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont(FONT_NAME, _resolve_font_path(settings)))
        _font_registered = True
    return FONT_NAME


def to_pdf_bytes(rows, columns, *, settings=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    font = _ensure_font(settings)
    header_style = ParagraphStyle('header', fontName=font, fontSize=9, leading=11, textColor=colors.white)
    cell_style = ParagraphStyle('cell', fontName=font, fontSize=8, leading=10)

    def escaped(value):
        text = '' if value is None else str(value)
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    data = [[Paragraph(escaped(REPORT_COLUMNS[key]), header_style) for key in columns]]
    for row in rows:
        data.append([Paragraph(escaped(_cell(row, key)), cell_style) for key in columns])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=24, bottomMargin=24, leftMargin=24, rightMargin=24)
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2F5FA3')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F6FB')]),
    ]))
    doc.build([table])
    return buffer.getvalue()


WRITERS = {
    'json': lambda rows, columns, settings=None: to_json_bytes(rows, columns),
    'xlsx': lambda rows, columns, settings=None: to_xlsx_bytes(rows, columns),
    'xls': lambda rows, columns, settings=None: to_xls_bytes(rows, columns),
    'pdf': lambda rows, columns, settings=None: to_pdf_bytes(rows, columns, settings=settings),
}
