"""Chart downloads in PNG and PDF (specification: "visualization when working with statistical data
(charts, graphs in png, pdf formats)"; D-222).

Each chart is laid out once as a list of drawing operations (rectangles, lines, text) in points with
a top-left origin; two small backends replay them — Pillow for PNG, reportlab for PDF — so both files
look the same. reportlab's own PNG renderer needs native Cairo, which the image does not have.
"""
import io
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas as pdf_canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import ALL_ROLES, AuthContext, require_roles
from .catalog_routes import university_scope
from .db import get_db
from .models import AnnualMetric, Launch, WorkflowStatus, WorkflowTemplate
from .report_routes import FONTS_DIR, register_pdf_fonts

router = APIRouter(prefix='/api/v1', tags=['Графики'])
any_role = require_roles(*ALL_ROLES)

# Palette mirrors the interface's chart tokens (frontend/src/styles.css, --chart-*).
TEXT = '#262336'
MUTED = '#635b72'
GRID = '#e4e1ec'
SERIES = ['#8854da', '#c6b1ee', '#6e98df', '#65ae9f']
PNG_SCALE = 2  # 2× pixels per point, so the PNG stays sharp on high-density screens and in slides


# ---------- drawing operations ----------

@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    fill: str


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: float = 1


@dataclass
class Text:
    x: float
    y: float  # baseline
    text: str
    size: float
    color: str = TEXT
    bold: bool = False
    anchor: Literal['start', 'middle', 'end'] = 'start'


@dataclass
class Figure:
    width: float
    height: float
    ops: list = field(default_factory=list)


_pil_fonts = {}


def _pil_font(size, bold):
    key = (round(size * PNG_SCALE), bold)
    if key not in _pil_fonts:
        _pil_fonts[key] = ImageFont.truetype(str(FONTS_DIR / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')), key[0])
    return _pil_fonts[key]


def text_width(text, size, bold=False):
    """Width in points, measured with the same font the renderers use."""
    return _pil_font(size, bold).getlength(text) / PNG_SCALE


def fit(text, size, max_width, bold=False):
    """Shortens `text` with an ellipsis until it fits `max_width` points."""
    if text_width(text, size, bold) <= max_width:
        return text
    while text and text_width(text + '…', size, bold) > max_width:
        text = text[:-1]
    return text.rstrip() + '…'


def render_png(fig: Figure) -> bytes:
    s = PNG_SCALE
    image = Image.new('RGB', (round(fig.width * s), round(fig.height * s)), 'white')
    draw = ImageDraw.Draw(image)
    for op in fig.ops:
        if isinstance(op, Rect):
            if op.h > 0 and op.w > 0:
                draw.rectangle([op.x * s, op.y * s, (op.x + op.w) * s - 1, (op.y + op.h) * s - 1], fill=op.fill)
        elif isinstance(op, Line):
            draw.line([op.x1 * s, op.y1 * s, op.x2 * s, op.y2 * s], fill=op.color, width=max(1, round(op.width * s)))
        elif isinstance(op, Text):
            anchor = {'start': 'ls', 'middle': 'ms', 'end': 'rs'}[op.anchor]
            draw.text((op.x * s, op.y * s), op.text, fill=op.color, font=_pil_font(op.size, op.bold), anchor=anchor)
    out = io.BytesIO()
    image.save(out, format='PNG', optimize=True)
    return out.getvalue()


def render_pdf(fig: Figure, title: str) -> bytes:
    register_pdf_fonts()
    out = io.BytesIO()
    c = pdf_canvas.Canvas(out, pagesize=(fig.width, fig.height))
    c.setTitle(title)
    flip = lambda y: fig.height - y
    for op in fig.ops:
        if isinstance(op, Rect):
            if op.h > 0 and op.w > 0:
                c.setFillColor(op.fill)
                c.rect(op.x, flip(op.y + op.h), op.w, op.h, stroke=0, fill=1)
        elif isinstance(op, Line):
            c.setStrokeColor(op.color)
            c.setLineWidth(op.width)
            c.line(op.x1, flip(op.y1), op.x2, flip(op.y2))
        elif isinstance(op, Text):
            c.setFillColor(op.color)
            c.setFont('DejaVuSans-Bold' if op.bold else 'DejaVuSans', op.size)
            draw = {'start': c.drawString, 'middle': c.drawCentredString, 'end': c.drawRightString}[op.anchor]
            draw(op.x, flip(op.y), op.text)
    c.showPage()
    c.save()
    return out.getvalue()


# ---------- layouts ----------

def axis_ticks(value, target=4):
    """Round tick values from 0 to just above `value`: the step is 1, 2, 2.5 or 5 × 10ⁿ, about
    `target` intervals, with ~5 % headroom so the value labels above the tallest bar fit."""
    value = max(value * 1.05, 1)
    rough = value / target
    magnitude = 10 ** math.floor(math.log10(rough))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= rough)
    step = max(step, 1)  # every chart counts things: no fractional ticks
    return [step * i for i in range(math.ceil(value / step) + 1)]


def _nice_max(value):
    return axis_ticks(value)[-1]


def _header(fig, title, subtitle, legend=()):
    fig.ops.append(Text(32, 42, title, 18, bold=True))
    fig.ops.append(Text(32, 64, subtitle, 11, MUTED))
    x = 32
    for label, color in legend:
        fig.ops.append(Rect(x, 82, 10, 10, color))
        fig.ops.append(Text(x + 16, 91, label, 11, MUTED))
        x += 16 + text_width(label, 11) + 24


def grouped_bar_chart(title, subtitle, categories, series, note=''):
    """Vertical bars, one group per category, one bar per series; values printed above the bars."""
    fig = Figure(900, 520)
    _header(fig, title, subtitle, [(name, color) for name, _, color in series])
    left, right, top, bottom = 72, fig.width - 32, 118, fig.height - 70
    ticks = axis_ticks(max([v for _, values, _ in series for v in values] + [0]))
    peak = ticks[-1]
    for value in ticks:
        y = bottom - (bottom - top) * value / peak
        fig.ops.append(Line(left, y, right, y, GRID))
        fig.ops.append(Text(left - 10, y + 4, f'{value:g}', 10, MUTED, anchor='end'))
    if categories:
        group = (right - left) / len(categories)
        bar = min(56, group * 0.7 / max(1, len(series)))
        for i, category in enumerate(categories):
            start = left + group * i + (group - bar * len(series)) / 2
            for j, (_, values, color) in enumerate(series):
                height = (bottom - top) * values[i] / peak
                x = start + bar * j
                fig.ops.append(Rect(x + 2, bottom - height, bar - 4, height, color))
                fig.ops.append(Text(x + bar / 2, bottom - height - 6, f'{values[i]:g}', 10, TEXT, anchor='middle'))
            fig.ops.append(Text(left + group * i + group / 2, bottom + 20, fit(str(category), 11, group - 8), 11, TEXT, anchor='middle'))
    else:
        fig.ops.append(Text((left + right) / 2, (top + bottom) / 2, 'Нет данных', 13, MUTED, anchor='middle'))
    if note:
        fig.ops.append(Text(32, fig.height - 24, note, 10, MUTED))
    return fig


def horizontal_bar_chart(title, subtitle, labels, values, color, note=''):
    """One bar per label, labels on the left — suits long names such as workflow statuses."""
    row = 30
    fig = Figure(900, 150 + row * max(1, len(labels)))
    _header(fig, title, subtitle)
    label_width = 280
    left, right, top = 32 + label_width, fig.width - 72, 110
    peak = _nice_max(max(values + [0]))
    for i, (label, value) in enumerate(zip(labels, values)):
        y = top + row * i
        fig.ops.append(Text(left - 12, y + 19, fit(label, 11, label_width - 12), 11, TEXT, anchor='end'))
        fig.ops.append(Rect(left, y + 6, right - left, row - 12, '#f3f0f7'))
        fig.ops.append(Rect(left, y + 6, (right - left) * value / peak, row - 12, color))
        fig.ops.append(Text(right + 10, y + 19, str(value), 11, TEXT, bold=True))
    if not labels:
        fig.ops.append(Text(fig.width / 2, top + 20, 'Нет данных', 13, MUTED, anchor='middle'))
    if note:
        fig.ops.append(Text(32, fig.height - 20, note, 10, MUTED))
    return fig


# ---------- charts ----------

def annual_chart(db):
    rows = list(db.scalars(select(AnnualMetric).order_by(AnnualMetric.year)))
    return grouped_bar_chart(
        'Интерес к обучению', 'Заявки и обучающиеся по годам',
        [r.year for r in rows],
        [('Заявки', [r.applications for r in rows], SERIES[0]), ('Обучающиеся', [r.students for r in rows], SERIES[1])],
        note='Полные календарные годы',
    )


def status_counts(db, user):
    """[(status name, interactions in it)] for the user's scope: every active status of every workflow
    that has interactions (default workflow first), in process order, including zeros."""
    counts = dict(db.execute(
        select(Launch.status_id, func.count()).where(university_scope(Launch.university_id, user)).group_by(Launch.status_id)
    ).all())
    statuses = db.execute(
        select(WorkflowStatus, WorkflowTemplate)
        .join(WorkflowTemplate, WorkflowTemplate.id == WorkflowStatus.template_id)
        .order_by(WorkflowTemplate.is_default.desc(), WorkflowTemplate.name, WorkflowStatus.position)
    ).all()
    used_templates = {s.template_id for s, _ in statuses if counts.get(s.id)} | {t.id for _, t in statuses if t.is_default}
    return [
        (s.name, counts.get(s.id, 0)) for s, t in statuses
        if t.id in used_templates and (s.is_active or counts.get(s.id))
    ]


def status_chart(db, user):
    pairs = status_counts(db, user)
    total = sum(n for _, n in pairs)
    return horizontal_bar_chart(
        'Цикл взаимодействия', f'Взаимодействия по статусам · всего {total}',
        [name for name, _ in pairs], [n for _, n in pairs], SERIES[0],
        note=f'Сформировано {datetime.now():%d.%m.%Y %H:%M}',
    )


CHARTS = {
    'annual': ('interest-by-year', 'Интерес к обучению', lambda db, user: annual_chart(db)),
    'interactions-by-status': ('interactions-by-status', 'Взаимодействия по статусам', status_chart),
}


@router.get('/charts/{chart}', summary='Скачать график (PNG или PDF)')
def download_chart(
    chart: Literal['annual', 'interactions-by-status'],
    format: Literal['png', 'pdf'] = Query(),
    auth: AuthContext = Depends(any_role),
    db: Session = Depends(get_db),
):
    filename, title, build = CHARTS[chart]
    fig = build(db, auth.user)
    if format == 'png':
        content, media_type = render_png(fig), 'image/png'
    else:
        content, media_type = render_pdf(fig, title), 'application/pdf'
    return Response(content, media_type=media_type,
                    headers={'Content-Disposition': f'attachment; filename="{filename}-{datetime.now():%Y%m%d}.{format}"'})
