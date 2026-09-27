"""Vector PDF charts generated from the same scoped snapshot as the analytics screen."""

from datetime import datetime
from html import escape
from io import BytesIO
from math import ceil
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .report_routes import register_pdf_fonts

VIOLET = colors.HexColor('#6957B5')
BLUE = colors.HexColor('#4985C5')
ORANGE = colors.HexColor('#D89A4F')
GREEN = colors.HexColor('#4A9B72')
GREY = colors.HexColor('#8A92A4')
INK = colors.HexColor('#26213A')
MUTED = colors.HexColor('#676478')
GRID = colors.HexColor('#DAD8E4')
PALETTE = [VIOLET, BLUE, ORANGE, GREEN, GREY]
MONTHS = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']


def date_label(iso: str) -> str:
    year, month, day = iso.split('-')
    return f'{day}.{month}.{year}'


def month_label(key: str) -> str:
    year, month = key.split('-')
    return f'{MONTHS[int(month) - 1]} {year}'


def section_title(value: str) -> Paragraph:
    return Paragraph(value, ParagraphStyle(
        'analytics-section', fontName='DejaVuSans-Bold', fontSize=15, leading=21,
        textColor=INK, spaceAfter=12,
    ))


def plain_text(value: str, *, size: int = 10, leading: int = 16) -> Paragraph:
    return Paragraph(value, ParagraphStyle(
        'analytics-text', fontName='DejaVuSans', fontSize=size, leading=leading,
        textColor=INK, spaceAfter=7,
    ))


def draw_empty(canvas, width: float):
    canvas.setFont('DejaVuSans', 11)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(width / 2, 120, 'Нет данных за выбранный период')


class StageChart(Flowable):
    def __init__(self, stages: list[dict], has_data: bool, width: float):
        super().__init__()
        self.stages, self.has_data, self.width = stages, has_data, width
        self.height = 255

    def draw(self):
        c = self.canv
        if not self.has_data:
            draw_empty(c, self.width)
            return
        maximum = max(1, *(row['count'] for row in self.stages))
        x0, bar_x, bar_width = 8, 190, self.width - 250
        for index, row in enumerate(self.stages):
            y = 220 - index * 43
            c.setFont('DejaVuSans', 10)
            c.setFillColor(INK)
            c.drawString(x0, y + 5, row['name'])
            c.setFillColor(GRID)
            c.roundRect(bar_x, y, bar_width, 19, 4, fill=1, stroke=0)
            if row['count']:
                c.setFillColor(PALETTE[index])
                c.roundRect(bar_x, y, bar_width * row['count'] / maximum, 19, 4, fill=1, stroke=0)
            c.setFont('DejaVuSans-Bold', 11)
            c.setFillColor(INK)
            c.drawRightString(self.width - 8, y + 5, str(row['count']))


class MonthChart(Flowable):
    def __init__(self, months: list[dict], has_data: bool, width: float):
        super().__init__()
        self.months, self.has_data, self.width = months, has_data, width
        self.height = 330

    def draw(self):
        c = self.canv
        if not self.has_data:
            draw_empty(c, self.width)
            return
        left, right, bottom, top = 64, self.width - 26, 66, 280
        maximum = max(1, *(month['count'] for month in self.months))
        ticks = sorted({0, ceil(maximum / 2), maximum})
        for tick in ticks:
            y = bottom + (top - bottom) * tick / maximum
            c.setStrokeColor(GRID)
            c.line(left, y, right, y)
            c.setFont('DejaVuSans', 8)
            c.setFillColor(MUTED)
            c.drawRightString(left - 12, y - 3, str(tick))
        c.setStrokeColor(MUTED)
        c.line(left, bottom, left, top)
        c.line(left, bottom, right, bottom)
        points = []
        for index, month in enumerate(self.months):
            x = left + (right - left) * (index + 0.5) / len(self.months)
            y = bottom + (top - bottom) * month['count'] / maximum
            points.append((x, y))
            c.setFont('DejaVuSans', 8)
            c.setFillColor(MUTED)
            c.drawCentredString(x, 48, month_label(month['month']))
            c.setFillColor(INK)
            c.drawCentredString(x, min(top + 8, y + 12), str(month['count']))
        c.setStrokeColor(VIOLET)
        c.setLineWidth(2.5)
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            c.line(x1, y1, x2, y2)
        for x, y in points:
            c.setFillColor(colors.white)
            c.circle(x, y, 4, fill=1, stroke=0)
            c.setStrokeColor(VIOLET)
            c.circle(x, y, 4, fill=0, stroke=1)
        c.setFillColor(INK)
        c.setFont('DejaVuSans', 9)
        c.drawCentredString((left + right) / 2, 25, 'Месяцы')
        c.saveState()
        c.translate(12, (bottom + top) / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, 'Внедрённые программы')
        c.restoreState()


class RankingChart(Flowable):
    def __init__(self, ranking: list[dict], width: float):
        super().__init__()
        self.ranking, self.width = ranking, width
        self.height = 350

    def draw(self):
        c = self.canv
        if not self.ranking:
            draw_empty(c, self.width)
            return
        left, right, bottom, top = 24, self.width - 20, 95, 305
        max_programs = max(1, *(row['programs'] for row in self.ranking))
        max_students = max(1, *(row['students'] for row in self.ranking))
        c.setStrokeColor(GRID)
        c.line(left, bottom, right, bottom)
        group_width = (right - left) / len(self.ranking)
        for index, row in enumerate(self.ranking):
            center = left + group_width * (index + 0.5)
            for value, maximum, dx, color in (
                (row['programs'], max_programs, -22, VIOLET),
                (row['students'], max_students, 9, BLUE),
            ):
                height = (top - bottom) * value / maximum if value else 0
                c.setFillColor(color)
                if height:
                    c.rect(center + dx, bottom, 21, height, fill=1, stroke=0)
                c.setFont('DejaVuSans-Bold', 9)
                c.setFillColor(INK)
                label = '0*' if value == 0 and color == BLUE else str(value)
                c.drawCentredString(center + dx + 10, bottom + height + 7, label)
            words = row['name'].split()
            lines = []
            line = ''
            for word in words:
                trial = f'{line} {word}'.strip()
                if line and c.stringWidth(trial, 'DejaVuSans', 8) > group_width - 8:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            if line:
                lines.append(line)
            c.setFont('DejaVuSans', 8)
            for line_number, line in enumerate(lines[:4]):
                c.drawCentredString(center, 78 - line_number * 10, line)
        c.setFont('DejaVuSans', 9)
        c.setFillColor(VIOLET)
        c.drawString(left, 30, '■  Внедрённые программы')
        c.setFillColor(BLUE)
        c.drawString(left + 215, 30, '■  Студенты')
        c.setFillColor(MUTED)
        c.setFont('DejaVuSans', 8)
        c.drawString(left, 18, 'Высота столбцов рассчитана отдельно для каждой категории.')
        if any(row['students'] == 0 for row in self.ranking):
            c.drawString(left, 5, '* 0 может означать незаполненные данные о студентах.')


def build_analytics_pdf(snapshot: dict) -> bytes:
    """Render all three charts, including clear empty states and every selected month."""
    register_pdf_fonts()
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=landscape(A4), leftMargin=42, rightMargin=42,
        topMargin=40, bottomMargin=36, title='Аналитика UniCRM', author='UniCRM',
    )
    width = landscape(A4)[0] - 84
    generated = datetime.now(ZoneInfo(snapshot['time_zone'])).strftime('%d.%m.%Y %H:%M')
    universities = ', '.join(snapshot['universities'])
    story = [
        Paragraph('Аналитика UniCRM', ParagraphStyle(
            'analytics-title', fontName='DejaVuSans-Bold', fontSize=21, leading=28,
            textColor=INK, spaceAfter=16,
        )),
        plain_text(f"Период: {date_label(snapshot['period_from'])} – {date_label(snapshot['period_to'])}"),
        plain_text(f'Вузы: {escape(universities)}'),
        plain_text(f'Дата формирования: {generated} ({escape(snapshot["time_zone"])})', size=9),
        Spacer(1, 22),
        section_title('Вузы по этапам'),
        plain_text('Вуз учитывается на достигнутом этапе и на всех предыдущих.', size=9),
        StageChart(snapshot['stages'], snapshot['has_stage_data'], width),
        PageBreak(),
    ]
    months = snapshot['monthly']
    month_pages = ([months[index:index + 12] for index in range(0, len(months), 12)] or [[]]) if snapshot['has_implementation_data'] else [[]]
    for index, chunk in enumerate(month_pages):
        title = 'Внедрённые программы по месяцам' + (' (продолжение)' if index else '')
        story.extend([
            section_title(title),
            plain_text('Дата внедрения — первый зафиксированный переход в «Обучение».', size=9),
            MonthChart(chunk, snapshot['has_implementation_data'], width),
            PageBreak(),
        ])
    story.extend([
        section_title('Рейтинг вузов'),
        plain_text('Топ-5 по числу внедрённых программ; при равенстве — по числу студентов.', size=9),
        RankingChart(snapshot['ranking'], width),
    ])
    if snapshot['ranking']:
        story.append(Spacer(1, 8))
        for row in snapshot['ranking']:
            students_label = '0*' if row['students'] == 0 else str(row['students'])
            story.append(plain_text(
                f"{escape(row['name'])}: {row['programs']} внедрённых программ, {students_label} студентов",
                size=8, leading=11,
            ))
    document.build(story)
    return output.getvalue()
