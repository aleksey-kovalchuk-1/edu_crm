from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from .models import Base, University, Launch, Task, StageEvent, AnnualMetric
from .schemas import UniversityInput, LaunchInput, StageInput, TaskInput
from .seed import seed
from .settings import load_settings, validate_database_url

STAGES = ['Поиск контакта', 'Уточнение интереса', 'Встреча', 'Обмен документами', 'Согласование документов', 'Подписание', 'Передача материалов и лицензий', 'Внедрение продукта', 'Обучение преподавателей', 'Актуализация программы', 'Проведение занятий', 'Обновление материалов', 'Повышение квалификации']

def serialize(record):
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}

def is_overdue(launch):
    return launch.deadline < date.today() and launch.stage < 10

def create_app(database_url=None, seed_demo=None):
    # The server calls create_app() with no arguments and reads the environment; tests pass values explicitly.
    if database_url is None:
        settings = load_settings()
        database_url = settings.database_url
        seed_demo = settings.seed_demo if seed_demo is None else seed_demo
    else:
        database_url = validate_database_url(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        if seed_demo:
            with Session(engine) as db:
                seed(db)
        yield
        engine.dispose()

    app = FastAPI(title='Образование CRM API', version='0.1.0', lifespan=lifespan, description='Демонстрационный шаблон. Авторизация и производственные интеграции ещё не реализованы.')

    def session():
        with Session(engine) as db:
            yield db

    def require(db, model, id):
        record = db.get(model, id)
        if record is None:
            raise HTTPException(404, 'Запись не найдена')
        return record

    @app.get('/api/v1/health')
    def health(db: Session = Depends(session)):
        db.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.get('/api/v1/stages')
    def stages():
        return STAGES

    @app.get('/api/v1/universities')
    def universities(db: Session = Depends(session)):
        return [serialize(x) for x in db.scalars(select(University).order_by(University.id))]

    @app.post('/api/v1/universities', status_code=201)
    def add_university(data: UniversityInput, db: Session = Depends(session)):
        record = University(**data.model_dump())
        db.add(record)
        db.commit()
        db.refresh(record)
        return serialize(record)

    @app.get('/api/v1/launches')
    def launches(db: Session = Depends(session)):
        return [{**serialize(l), 'university': u.name, 'city': u.city, 'overdue': is_overdue(l)} for l,u in db.execute(select(Launch, University).join(University).order_by(Launch.id))]

    @app.post('/api/v1/launches', status_code=201)
    def add_launch(data: LaunchInput, db: Session = Depends(session)):
        require(db, University, data.university_id)
        record = Launch(**data.model_dump(), stage=0)
        db.add(record)
        db.flush()
        db.add(StageEvent(launch_id=record.id, stage=0))
        db.commit()
        db.refresh(record)
        return serialize(record)

    @app.patch('/api/v1/launches/{id}')
    def update_stage(id: int, data: StageInput, db: Session = Depends(session)):
        record = require(db, Launch, id)
        if record.stage != data.stage:
            record.stage = data.stage
            db.add(StageEvent(launch_id=id, stage=data.stage))
            db.commit()
        return serialize(record)

    @app.get('/api/v1/launches/{id}/history')
    def history(id: int, db: Session = Depends(session)):
        require(db, Launch, id)
        return [serialize(x) for x in db.scalars(select(StageEvent).where(StageEvent.launch_id == id).order_by(StageEvent.id.desc()))]

    @app.get('/api/v1/tasks')
    def tasks(db: Session = Depends(session)):
        return [serialize(x) for x in db.scalars(select(Task).order_by(Task.deadline, Task.id))]

    @app.patch('/api/v1/tasks/{id}')
    def update_task(id: int, data: TaskInput, db: Session = Depends(session)):
        record = require(db, Task, id)
        record.done = data.done
        db.commit()
        return serialize(record)

    @app.get('/api/v1/dashboard')
    def dashboard(db: Session = Depends(session)):
        rows = list(db.scalars(select(Launch)))
        return {'universities': len(list(db.scalars(select(University.id)))), 'launches': len(rows), 'students': sum(x.students for x in rows), 'overdue': sum(is_overdue(x) for x in rows), 'annual': [serialize(x) for x in db.scalars(select(AnnualMetric).order_by(AnnualMetric.year))]}

    return app
