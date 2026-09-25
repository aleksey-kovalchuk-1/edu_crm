"""Chart downloads (D-222): the specification's "charts, graphs in png, pdf formats"."""
import io

from PIL import Image
from sqlalchemy import delete

from app.chart_routes import fit, grouped_bar_chart, horizontal_bar_chart, render_pdf, render_png, status_counts
from app.models import AnnualMetric, User
from helpers import database, login


def create_launch(client, university_id, program='Python'):
    response = client.post('/api/v1/launches', json={
        'university_id': university_id, 'program': program, 'product': 'Учебная среда', 'owner': 'Ирина Петрова',
        'students': 30, 'deadline': '2026-10-01',
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_annual_chart_downloads_as_png_and_pdf(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-user',))
    with database(database_url) as db:
        db.execute(delete(AnnualMetric))
        db.add_all([AnnualMetric(year=2024, applications=110, students=72, streams=4),
                    AnnualMetric(year=2025, applications=120, students=80, streams=4)])
        db.commit()

    png = client.get('/api/v1/charts/annual', params={'format': 'png'})
    assert png.status_code == 200, png.text
    assert png.headers['content-type'] == 'image/png'
    assert 'attachment' in png.headers['content-disposition'] and '.png' in png.headers['content-disposition']
    image = Image.open(io.BytesIO(png.content))
    assert image.size == (1800, 1040)  # 900×520 pt at 2×

    pdf = client.get('/api/v1/charts/annual', params={'format': 'pdf'})
    assert pdf.status_code == 200
    assert pdf.headers['content-type'] == 'application/pdf'
    assert pdf.content.startswith(b'%PDF') and b'DejaVuSans' in pdf.content


def test_status_chart_counts_only_interactions_in_scope(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university = client.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва', 'contact': ''}).json()
    create_launch(client, university['id'], 'A')
    create_launch(client, university['id'], 'B')

    with database(database_url) as db:
        supervisor = db.query(User).filter(User.roles.any('crm-supervisor')).first()
        pairs = status_counts(db, supervisor)
        manager = User(keycloak_sub='kc-other', email='', full_name='Без вузов', roles=['crm-user'], is_active=True)
        db.add(manager)
        db.commit()
        nobody = status_counts(db, manager)
    assert pairs[0][1] == 2  # both start in the default workflow's first status
    assert sum(n for _, n in pairs) == 2
    assert [name for name, _ in pairs] == [name for name, _ in nobody]  # same statuses, including zeros
    assert sum(n for _, n in nobody) == 0

    png = client.get('/api/v1/charts/interactions-by-status', params={'format': 'png'})
    assert png.status_code == 200
    assert Image.open(io.BytesIO(png.content)).format == 'PNG'


def test_chart_requests_are_validated_and_need_a_session(client, keycloak, database_url):
    assert client.get('/api/v1/charts/annual', params={'format': 'png'}).status_code == 401
    login(client, keycloak)
    assert client.get('/api/v1/charts/annual', params={'format': 'svg'}).status_code == 422
    assert client.get('/api/v1/charts/salaries', params={'format': 'png'}).status_code == 422


def test_layouts_render_empty_and_long_labels():
    empty = grouped_bar_chart('Пусто', 'нет данных', [], [('Заявки', [], '#8854da')])
    assert render_png(empty).startswith(b'\x89PNG')
    long = horizontal_bar_chart('Статусы', 'длинные названия', ['Очень длинное название статуса ' * 5], [3], '#8854da')
    assert render_pdf(long, 'x').startswith(b'%PDF')
    assert fit('Очень длинное название статуса ' * 5, 11, 200).endswith('…')


def test_axis_ticks_are_round_and_just_above_the_data():
    from app.chart_routes import axis_ticks
    assert axis_ticks(120) == [0, 50, 100, 150]
    assert axis_ticks(3) == [0, 1, 2, 3, 4]
    assert axis_ticks(0) == [0, 1]  # counts never get fractional ticks
