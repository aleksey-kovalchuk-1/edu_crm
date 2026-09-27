"""Interaction analytics use recorded history and enforce the viewer's university scope."""
from io import BytesIO
from datetime import datetime, timezone
from urllib.parse import unquote

from pypdf import PdfReader
from sqlalchemy import select

from app.analytics_pdf import build_analytics_pdf
from app.models import Launch, StatusChange, University
from helpers import database, login

PATH = '/api/v1/analytics/interactions'
PERIOD = {'period_from': '2026-01-01', 'period_to': '2026-03-31', 'time_zone': 'Asia/Tokyo'}


def create_university(client, name):
    response = client.post('/api/v1/universities', json={'name': name, 'city': 'Москва', 'contact': ''})
    assert response.status_code == 201, response.text
    return response.json()['id']


def create_interaction(client, university_id, *, program='Программа', students=12):
    response = client.post('/api/v1/launches', json={
        'university_id': university_id, 'program': program, 'product': 'Платформа',
        'owner': 'Ирина Петрова', 'students': students, 'deadline': '2026-04-01',
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


def set_history_dates(database_url, launch_id, dates):
    with database(database_url) as db:
        changes = list(db.scalars(select(StatusChange).where(StatusChange.launch_id == launch_id).order_by(StatusChange.id)))
        assert len(changes) == len(dates)
        for change, when in zip(changes, dates, strict=True):
            change.created_at = when
        db.commit()


def test_analytics_validates_period_and_timezone_on_server(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    inverted = client.get(PATH, params={**PERIOD, 'period_from': '2026-04-01'})
    assert inverted.status_code == 422
    assert inverted.json()['details'][0]['field'] == 'period_to'
    invalid_zone = client.get(PATH, params={**PERIOD, 'time_zone': 'not/a-zone'})
    assert invalid_zone.status_code == 422
    too_long = client.get(PATH, params={**PERIOD, 'period_from': '2015-01-01', 'period_to': '2026-01-01'})
    assert too_long.status_code == 422
    assert '10 лет' in too_long.json()['details'][0]['message']


def test_comment_without_status_change_does_not_enter_period_funnel(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    launch_id = create_interaction(client, create_university(client, 'Вуз с комментарием'))
    assert client.patch(f'/api/v1/launches/{launch_id}', json={'stage': 8}).status_code == 200
    with database(database_url) as db:
        status_id = db.get(Launch, launch_id).status_id
    note = client.post(f'/api/v1/launches/{launch_id}/status-changes',
                       data={'status_id': str(status_id), 'comment': 'Обсудили детали'})
    assert note.status_code == 201, note.text
    set_history_dates(database_url, launch_id, [
        datetime(2025, 12, 1, tzinfo=timezone.utc),
        datetime(2025, 12, 2, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    ])

    response = client.get(PATH, params=PERIOD)
    assert response.status_code == 200
    assert [row['count'] for row in response.json()['stages']] == [0, 0, 0, 0, 0]


def test_empty_period_returns_empty_states_and_zero_month_slots(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    create_interaction(client, create_university(client, 'Вуз без событий в периоде'))

    response = client.get(PATH, params={**PERIOD, 'period_from': '2040-01-01', 'period_to': '2040-03-31'})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body['has_stage_data'] is False
    assert body['has_implementation_data'] is False
    assert [row['count'] for row in body['stages']] == [0, 0, 0, 0, 0]
    assert body['monthly'] == [
        {'month': '2040-01', 'count': 0}, {'month': '2040-02', 'count': 0}, {'month': '2040-03', 'count': 0},
    ]
    assert body['ranking'] == []


def test_analytics_counts_transitions_with_local_month_and_period_boundaries(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university_id = create_university(client, 'Вуз Восток')
    launch_id = create_interaction(client, university_id)
    assert client.patch(f'/api/v1/launches/{launch_id}', json={'stage': 7}).status_code == 200
    assert client.patch(f'/api/v1/launches/{launch_id}', json={'stage': 8}).status_code == 200
    set_history_dates(database_url, launch_id, [
        datetime(2025, 12, 31, 16, tzinfo=timezone.utc),  # 1 Jan in Tokyo.
        datetime(2026, 1, 15, 12, tzinfo=timezone.utc),
        datetime(2026, 1, 31, 16, tzinfo=timezone.utc),  # 1 Feb in Tokyo, implementation.
    ])

    response = client.get(PATH, params=PERIOD)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row['count'] for row in body['stages']] == [1, 1, 1, 1, 0]
    assert body['monthly'] == [
        {'month': '2026-01', 'count': 0}, {'month': '2026-02', 'count': 1}, {'month': '2026-03', 'count': 0},
    ]
    assert body['ranking'] == [{'id': university_id, 'name': 'Вуз Восток', 'programs': 1, 'students': 12}]


def test_manager_scope_applies_to_counts_and_rejects_private_university(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    shared_id = create_university(client, 'Общий вуз')
    private_id = create_university(client, 'Чужой вуз')
    shared_launch = create_interaction(client, shared_id, program='Общая программа')
    private_launch = create_interaction(client, private_id, program='Чужая программа')
    with database(database_url) as db:
        db.get(University, shared_id).team_visible_to_managers = True
        db.commit()
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    set_history_dates(database_url, shared_launch, [start])
    set_history_dates(database_url, private_launch, [start])
    login(client, keycloak, roles=('crm-user',), subject='kc-manager', name='Менеджер', email='manager@example.test')

    response = client.get(PATH, params=PERIOD)

    assert response.status_code == 200, response.text
    assert [row['count'] for row in response.json()['stages']] == [1, 0, 0, 0, 0]
    assert response.json()['universities'] == ['Все вузы']
    assert client.get(PATH, params={**PERIOD, 'university_id': private_id}).status_code == 404
    selected = client.get(PATH, params={**PERIOD, 'university_id': shared_id})
    assert selected.status_code == 200
    assert selected.json()['universities'] == ['Общий вуз']


def pdf_text(response):
    return '\n'.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)


def test_pdf_uses_same_scoped_values_and_selected_header_as_json(client, keycloak, database_url):
    login(client, keycloak, roles=('crm-supervisor',))
    university_id = create_university(client, 'Вуз Восток')
    launch_id = create_interaction(client, university_id, students=26)
    assert client.patch(f'/api/v1/launches/{launch_id}', json={'stage': 8}).status_code == 200
    set_history_dates(database_url, launch_id, [
        datetime(2026, 1, 15, tzinfo=timezone.utc),
        datetime(2026, 2, 3, tzinfo=timezone.utc),
    ])
    params = {**PERIOD, 'university_id': university_id}
    snapshot = client.get(PATH, params=params).json()
    response = client.get(f'{PATH}.pdf', params=params)

    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert 'Аналитика_UniCRM_01.01.2026-31.03.2026.pdf' in unquote(response.headers['content-disposition'])
    assert response.headers['cache-control'] == 'no-store'
    reader = PdfReader(BytesIO(response.content))
    text = pdf_text(response)
    for label in ('Вузы по этапам', 'Внедрённые программы по месяцам', 'Рейтинг вузов',
                  '01.01.2026 – 31.03.2026', 'Вуз Восток', 'Дата формирования:',
                  'Янв 2026', 'Фев 2026', 'Мар 2026', 'Студенты'):
        assert label in text
    assert snapshot['monthly'] == [
        {'month': '2026-01', 'count': 0}, {'month': '2026-02', 'count': 1}, {'month': '2026-03', 'count': 0},
    ]
    assert '26' in text
    assert any('/FontFile2' in str(font.get_object().get('/FontDescriptor'))
               for page in reader.pages for font in page['/Resources']['/Font'].values())


def test_pdf_enforces_auth_scope_and_displays_all_three_empty_states(client, keycloak, database_url):
    assert client.get(f'{PATH}.pdf', params=PERIOD).status_code == 401
    login(client, keycloak, roles=('crm-supervisor',))
    private_id = create_university(client, 'Закрытый вуз')
    shared_id = create_university(client, 'Доступный вуз')
    with database(database_url) as db:
        db.get(University, shared_id).team_visible_to_managers = True
        db.commit()
    login(client, keycloak, roles=('crm-user',), subject='kc-manager-pdf', name='Менеджер', email='manager-pdf@example.test')
    assert client.get(f'{PATH}.pdf', params={**PERIOD, 'university_id': private_id}).status_code == 404
    assert client.get(f'{PATH}.pdf', params={**PERIOD, 'period_from': '2026-04-01'}).status_code == 422
    assert client.get(f'{PATH}.pdf', params={**PERIOD, 'period_from': '2015-01-01'}).status_code == 422
    response = client.get(f'{PATH}.pdf', params={**PERIOD, 'university_id': shared_id})
    assert response.status_code == 200
    text = pdf_text(response)
    assert 'Доступный вуз' in text
    assert 'Закрытый вуз' not in text
    assert text.count('Нет данных за выбранный период') == 3
    all_accessible = pdf_text(client.get(f'{PATH}.pdf', params=PERIOD))
    assert 'Все вузы' in all_accessible
    assert 'Закрытый вуз' not in all_accessible


def test_pdf_keeps_every_month_of_a_long_period():
    months = [{'month': f'{year}-{month:02d}', 'count': int(year == 2027 and month == 1)}
              for year in (2026, 2027) for month in range(1, 13)]
    snapshot = {
        'period_from': '2026-01-01', 'period_to': '2027-12-31', 'time_zone': 'Europe/Moscow',
        'universities': ['Все вузы'],
        'stages': [{'name': name, 'count': 0} for name in
                   ('Первый контакт', 'Документы', 'Внедрение', 'Обучение', 'Сопровождение')],
        'monthly': months, 'ranking': [{'id': 1, 'name': 'ИТМО', 'programs': 1, 'students': 14}],
        'has_stage_data': False, 'has_implementation_data': True,
    }
    reader = PdfReader(BytesIO(build_analytics_pdf(snapshot)))
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert len(reader.pages) == 4  # Funnel, two monthly chart pages, ranking.
    assert 'Янв 2026' in text and 'Дек 2027' in text
    assert 'ИТМО: 1 внедрённых программ, 14 студентов' in text


def test_pdf_qualifies_a_recorded_zero_students_value():
    snapshot = {
        'period_from': '2026-01-01', 'period_to': '2026-01-31', 'time_zone': 'UTC',
        'universities': ['Все вузы'],
        'stages': [{'name': 'Первый контакт', 'count': 1}],
        'monthly': [{'month': '2026-01', 'count': 1}],
        'ranking': [{'id': 1, 'name': 'Вуз с неизвестным набором', 'programs': 1, 'students': 0}],
        'has_stage_data': True, 'has_implementation_data': True,
    }
    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(build_analytics_pdf(snapshot))).pages)
    assert '0* студентов' in text
    assert '0 может означать незаполненные данные' in text
