from datetime import date, timedelta
from sqlalchemy import select
from .models import University, Launch, Task, StageEvent, AnnualMetric

def seed(db):
    if db.scalar(select(University.id).limit(1)) is not None:
        return
    # Fictional institutions and people; no real customer data.
    universities = [
        ('Северный технологический университет', 'Санкт-Петербург', 'Анна Соколова'),
        ('Волжский институт цифровых технологий', 'Казань', 'Илья Орлов'),
        ('Уральская инженерная академия', 'Екатеринбург', 'Мария Лебедева'),
        ('Столичный университет прикладных наук', 'Москва', 'Дмитрий Волков'),
        ('Сибирский цифровой университет', 'Новосибирск', 'Елена Морозова'),
        ('Южный институт информационных систем', 'Ростов-на-Дону', 'Алексей Белов'),
    ]
    records = [University(name=n, city=c, contact=p) for n, c, p in universities]
    db.add_all(records)
    db.flush()
    courses = [
        (0, 'Разработка на Python', 'Python / Jupyter', 8, 120, 12),
        (1, 'Аналитика данных', 'PostgreSQL / Superset', 4, 80, 5),
        (2, 'Облачные технологии', 'Docker / Linux', 6, 60, -2),
        (3, 'Разработка веб-приложений', 'React / TypeScript', 10, 150, 30),
        (4, 'Информационная безопасность', 'Linux', 2, 45, 18),
        (5, 'Работа с базами данных', 'PostgreSQL', 0, 40, 25),
        (0, 'Визуализация данных', 'Apache Superset', 5, 70, 9),
        (2, 'Прикладное программирование', 'Python / FastAPI', 11, 90, 45),
    ]
    owners = ['Анна Петрова', 'Михаил Смирнов', 'Ольга Кузнецова']
    for i, (u, program, product, stage, students, days) in enumerate(courses):
        launch = Launch(university_id=records[u].id, program=program, product=product, stage=stage, students=students, owner=owners[i % 3], deadline=date.today() + timedelta(days=days))
        db.add(launch)
        db.flush()
        db.add(StageEvent(launch_id=launch.id, stage=stage))
        db.add(Task(launch_id=launch.id, title=['Согласовать программу обучения', 'Получить подписанный договор', 'Проверить установку продукта', 'Подтвердить состав потока'][i % 4], owner=launch.owner, deadline=date.today() + timedelta(days=i-2)))
    db.add_all([AnnualMetric(year=y, applications=a, students=s, streams=f) for y,a,s,f in [(2023,420,320,12),(2024,610,470,17),(2025,890,715,25)]])
    db.commit()
