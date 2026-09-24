"""Interaction reports (docs/specification.md, "Functional requirements"; D-221).

A report is the list of interactions (launches) the user can see, filtered by period, universities,
IT directions, IT products, responsible and status, with the columns the user picked. The same
query feeds the on-screen preview (JSON) and the xlsx / xls / pdf downloads.

Period (D-221): an interaction belongs to a period when its launch date (`deadline`) or any of its
status changes falls inside it — i.e. something happened with it in that period.
"""
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Literal

import openpyxl
import xlwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, selectinload

from .audit import record_event
from .auth import ALL_ROLES, AuthContext, require_roles
from .catalog_routes import university_scope
from .db import get_db
from .errors import AppError, ErrorCode
from .models import ITProduct, Launch, StatusChange, University, WorkflowStatus, WorkflowTemplate, it_product_directions

router = APIRouter(prefix='/api/v1', tags=['Отчёты'])
any_role = require_roles(*ALL_ROLES)

# key, label, in the default selection. The first five defaults are the specification's columns.
COLUMNS: list[tuple[str, str, bool]] = [
    ('university', 'Учебное заведение', True),
    ('program', 'Программа', True),
    ('it_direction', 'ИТ-направление', True),
    ('it_product', 'ИТ-продукт', True),
    ('status', 'Статус', True),
    ('owner', 'Ответственный', True),
    ('city', 'Город', False),
    ('students', 'Обучающихся', False),
    ('deadline', 'Срок запуска', False),
    ('last_change', 'Последнее изменение статуса', False),
    ('comment', 'Последний комментарий', False),
]
COLUMN_LABELS = {key: label for key, label, _ in COLUMNS}
DEFAULT_COLUMNS = [key for key, _, default in COLUMNS if default]
MAX_PREVIEW_ROWS = 200

FONTS_DIR = Path(__file__).parent / 'fonts'
_fonts_registered = False


def validation_error(field, message):
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': field, 'message': message, 'type': 'value_error'}])


@dataclass
class ReportFilters:
    period_from: date | None
    period_to: date | None
    university_id: list[int]
    it_direction_id: list[int]
    it_product_id: list[int]
    owner: list[str]
    status_id: list[int]
    columns: list[str]

    def as_payload(self):
        return {
            'period_from': self.period_from.isoformat() if self.period_from else None,
            'period_to': self.period_to.isoformat() if self.period_to else None,
            'university_id': self.university_id, 'it_direction_id': self.it_direction_id,
            'it_product_id': self.it_product_id, 'owner': self.owner, 'status_id': self.status_id,
        }


def report_filters(
    period_from: date | None = None,
    period_to: date | None = None,
    university_id: list[int] = Query(default=[]),
    it_direction_id: list[int] = Query(default=[]),
    it_product_id: list[int] = Query(default=[]),
    owner: list[str] = Query(default=[]),
    status_id: list[int] = Query(default=[]),
    column: list[str] = Query(default=[]),
) -> ReportFilters:
    if period_from and period_to and period_from > period_to:
        raise validation_error('period_to', 'Конец периода раньше начала')
    unknown = [c for c in column if c not in COLUMN_LABELS]
    if unknown:
        raise validation_error('column', f'Неизвестные колонки: {", ".join(unknown)}')
    columns = list(dict.fromkeys(column)) or DEFAULT_COLUMNS  # keep the user's order, drop repeats
    owners = [o.strip() for o in owner if o.strip()]
    return ReportFilters(period_from, period_to, university_id, it_direction_id, it_product_id, owners, status_id, columns)


def _day_start(day):
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def report_query(user, f: ReportFilters):
    query = (
        select(Launch, University, WorkflowStatus)
        .join(University, University.id == Launch.university_id)
        .join(WorkflowStatus, WorkflowStatus.id == Launch.status_id)
        .where(university_scope(Launch.university_id, user))
    )
    if f.university_id:
        query = query.where(Launch.university_id.in_(f.university_id))
    if f.it_product_id:
        query = query.where(Launch.it_product_id.in_(f.it_product_id))
    if f.it_direction_id:
        in_direction = select(it_product_directions.c.it_product_id).where(it_product_directions.c.it_direction_id.in_(f.it_direction_id))
        query = query.where(Launch.it_product_id.in_(in_direction))
    if f.owner:
        query = query.where(Launch.owner.in_(f.owner))
    if f.status_id:
        query = query.where(Launch.status_id.in_(f.status_id))
    if f.period_from or f.period_to:
        deadline_in = []
        changed_in = [StatusChange.launch_id == Launch.id]
        if f.period_from:
            deadline_in.append(Launch.deadline >= f.period_from)
            changed_in.append(StatusChange.created_at >= _day_start(f.period_from))
        if f.period_to:
            deadline_in.append(Launch.deadline <= f.period_to)
            changed_in.append(StatusChange.created_at < _day_start(f.period_to + timedelta(days=1)))
        query = query.where(or_(and_(*deadline_in), exists().where(*changed_in)))
    return query.order_by(University.name, Launch.program, Launch.id)


def build_report(db: Session, user, f: ReportFilters):
    """Rows as dicts of display strings/numbers, keyed by the selected columns, plus the total."""
    records = db.execute(report_query(user, f)).all()
    launch_ids = [launch.id for launch, _, _ in records]
    product_ids = {launch.it_product_id for launch, _, _ in records if launch.it_product_id}
    products = {
        p.id: p for p in db.scalars(select(ITProduct).where(ITProduct.id.in_(product_ids)).options(selectinload(ITProduct.directions)))
    } if product_ids else {}
    last_change = {}
    if launch_ids and {'last_change', 'comment'} & set(f.columns):
        for change in db.scalars(
            select(StatusChange).where(StatusChange.launch_id.in_(launch_ids))
            .order_by(StatusChange.launch_id, StatusChange.created_at.desc(), StatusChange.id.desc())
        ):
            last_change.setdefault(change.launch_id, change)

    rows = []
    for launch, university, status in records:
        product = products.get(launch.it_product_id)
        change = last_change.get(launch.id)
        values = {
            'university': university.name,
            'program': launch.program,
            'it_direction': ', '.join(d.name for d in product.directions) if product else '',
            'it_product': f'{product.vendor} — {product.name}' if product else launch.product,
            'status': status.name,
            'owner': launch.owner,
            'city': university.city,
            'students': launch.students,
            'deadline': launch.deadline.strftime('%d.%m.%Y'),
            'last_change': change.created_at.strftime('%d.%m.%Y') if change else '',
            'comment': change.comment if change else '',
        }
        rows.append({key: values[key] for key in f.columns})
    return rows


def columns_out(keys):
    return [{'key': key, 'label': COLUMN_LABELS[key]} for key in keys]


@router.get('/reports/options', summary='Справочные значения для конструктора отчётов')
def report_options(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    owners = db.scalars(
        select(Launch.owner).where(university_scope(Launch.university_id, auth.user)).distinct().order_by(Launch.owner)
    ).all()
    statuses = db.execute(
        select(WorkflowStatus, WorkflowTemplate.name).join(WorkflowTemplate, WorkflowTemplate.id == WorkflowStatus.template_id)
        .where(WorkflowStatus.is_active.is_(True)).order_by(WorkflowTemplate.name, WorkflowStatus.position)
    ).all()
    return {
        'owners': list(owners),
        'statuses': [{'id': s.id, 'name': s.name, 'workflow': workflow} for s, workflow in statuses],
        'columns': [{'key': key, 'label': label, 'default': default} for key, label, default in COLUMNS],
    }


@router.get('/reports/interactions', summary='Отчёт по взаимодействиям (предпросмотр)')
def interactions_report(f: ReportFilters = Depends(report_filters), auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
    rows = build_report(db, auth.user, f)
    return {'columns': columns_out(f.columns), 'rows': rows[:MAX_PREVIEW_ROWS], 'total': len(rows)}


# ---------- files ----------

def _xlsx(columns, rows):
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = 'Взаимодействия'
    sheet.append([c['label'] for c in columns])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([row[c['key']] for c in columns])
    for i, c in enumerate(columns, start=1):
        longest = max([len(str(c['label']))] + [len(str(r[c['key']])) for r in rows])
        sheet.column_dimensions[get_column_letter(i)].width = min(60, longest + 2)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _xls(columns, rows):
    book = xlwt.Workbook(encoding='utf-8')
    sheet = book.add_sheet('Взаимодействия')
    bold = xlwt.easyxf('font: bold on')
    for j, c in enumerate(columns):
        sheet.write(0, j, c['label'], bold)
        longest = max([len(str(c['label']))] + [len(str(r[c['key']])) for r in rows])
        sheet.col(j).width = 256 * min(60, longest + 2)
    for i, row in enumerate(rows, start=1):
        for j, c in enumerate(columns):
            sheet.write(i, j, row[c['key']])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _register_fonts():
    global _fonts_registered
    if not _fonts_registered:
        pdfmetrics.registerFont(TTFont('DejaVuSans', str(FONTS_DIR / 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', str(FONTS_DIR / 'DejaVuSans-Bold.ttf')))
        _fonts_registered = True


def _pdf(columns, rows, subtitle):
    _register_fonts()
    body = ParagraphStyle('cell', fontName='DejaVuSans', fontSize=8, leading=10)
    head = ParagraphStyle('head', parent=body, fontName='DejaVuSans-Bold')
    title = ParagraphStyle('title', fontName='DejaVuSans-Bold', fontSize=14, leading=18)
    meta = ParagraphStyle('meta', fontName='DejaVuSans', fontSize=9, leading=12, textColor=colors.HexColor('#4b435c'))

    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title='Отчёт по взаимодействиям с учебными заведениями')
    esc = lambda v: str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    data = [[Paragraph(esc(c['label']), head) for c in columns]]
    data += [[Paragraph(esc(row[c['key']]), body) for c in columns] for row in rows]
    if not rows:
        data.append([Paragraph('Нет взаимодействий по выбранным условиям', body)] + [''] * (len(columns) - 1))
    table = Table(data, repeatRows=1, colWidths=[doc.width / len(columns)] * len(columns))
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1eafa')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e4e1ec')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    doc.build([Paragraph('Отчёт по взаимодействиям с учебными заведениями', title), Paragraph(esc(subtitle), meta), Spacer(1, 4 * mm), table])
    return out.getvalue()


FORMATS = {
    'xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', _xlsx),
    'xls': ('application/vnd.ms-excel', _xls),
}


@router.get('/reports/interactions/export', summary='Скачать отчёт по взаимодействиям (xlsx, xls, pdf)')
def export_interactions_report(
    request: Request,
    format: Literal['xlsx', 'xls', 'pdf'] = Query(),
    f: ReportFilters = Depends(report_filters),
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    rows = build_report(db, auth.user, f)
    columns = columns_out(f.columns)
    if format == 'pdf':
        period = ' — '.join(d.strftime('%d.%m.%Y') if d else '…' for d in (f.period_from, f.period_to)) if (f.period_from or f.period_to) else 'весь период'
        subtitle = f'Период: {period} · Взаимодействий: {len(rows)} · Сформирован {datetime.now():%d.%m.%Y %H:%M}, {auth.user.full_name}'
        content, media_type = _pdf(columns, rows, subtitle), 'application/pdf'
    else:
        media_type, writer = FORMATS[format]
        content = writer(columns, rows)
    record_event(db, request, auth.user, 'report.export', entity_type='report',
                 summary=f'Выгружен отчёт по взаимодействиям ({format}, строк: {len(rows)})',
                 payload={'format': format, 'rows': len(rows), 'columns': f.columns, 'filters': f.as_payload()})
    db.commit()
    filename = f'interactions-report-{date.today():%Y%m%d}.{format}'
    return Response(content, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="{filename}"'})
