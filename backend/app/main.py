from contextlib import asynccontextmanager
from datetime import date

import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from .auth import ALL_ROLES, ROLE_ADMIN, ROLE_SUPERVISOR, require_roles, router as auth_router
from .db import get_db
from .errors import AppError, ErrorCode, install_error_handlers
from .models import University, Launch, Task, StageEvent, AnnualMetric
from .oidc import OIDCClient
from .schemas import UniversityInput, LaunchInput, StageInput, TaskInput
from .security import TokenCipher
from .settings import load_settings, validate_database_url

STAGES = ['Поиск контакта', 'Уточнение интереса', 'Встреча', 'Обмен документами', 'Согласование документов', 'Подписание', 'Передача материалов и лицензий', 'Внедрение продукта', 'Обучение преподавателей', 'Актуализация программы', 'Проведение занятий', 'Обновление материалов', 'Повышение квалификации']

any_role = require_roles(*ALL_ROLES)
# Universities are catalog data; heads and administrators maintain catalogs (D-128).
catalog_editor = require_roles(ROLE_SUPERVISOR, ROLE_ADMIN)


def serialize(record):
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def is_overdue(launch):
    return launch.deadline < date.today() and launch.stage < 10


def require(db, model, id):
    record = db.get(model, id)
    if record is None:
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    return record


def create_app(settings=None, *, http_client=None):
    # The server calls create_app() and reads the environment; tests pass settings and a fake identity provider.
    settings = load_settings() if settings is None else settings
    validate_database_url(settings.database_url)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    owns_http_client = http_client is None
    http = http_client or httpx.Client(timeout=10)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()
        if owns_http_client:
            http.close()

    # Documentation lives under /api because nginx only proxies that prefix to the API.
    app = FastAPI(
        title='Образование CRM API',
        version='0.1.0',
        lifespan=lifespan,
        description='CRM взаимодействия с учебными заведениями. Вход — через Keycloak (`/api/v1/auth/login`); коды ошибок — docs/api/errors.md.',
        docs_url='/api/docs',
        redoc_url='/api/redoc',
        openapi_url='/api/openapi.json',
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(bind=engine)
    app.state.oidc = OIDCClient(
        issuer=settings.oidc_issuer,
        internal_base_url=settings.oidc_internal_base_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        http=http,
    )
    app.state.cipher = TokenCipher(settings.session_encryption_key)
    install_error_handlers(app)
    app.include_router(auth_router)

    @app.get('/api/v1/health')
    def health(db: Session = Depends(get_db)):
        db.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.get('/api/v1/stages', dependencies=[Depends(any_role)])
    def stages():
        return STAGES

    @app.get('/api/v1/universities', dependencies=[Depends(any_role)])
    def universities(db: Session = Depends(get_db)):
        return [serialize(x) for x in db.scalars(select(University).order_by(University.id))]

    @app.post('/api/v1/universities', status_code=201, dependencies=[Depends(catalog_editor)])
    def add_university(data: UniversityInput, db: Session = Depends(get_db)):
        record = University(**data.model_dump())
        db.add(record)
        db.commit()
        db.refresh(record)
        return serialize(record)

    @app.get('/api/v1/launches', dependencies=[Depends(any_role)])
    def launches(db: Session = Depends(get_db)):
        return [{**serialize(l), 'university': u.name, 'city': u.city, 'overdue': is_overdue(l)} for l, u in db.execute(select(Launch, University).join(University).order_by(Launch.id))]

    @app.post('/api/v1/launches', status_code=201, dependencies=[Depends(any_role)])
    def add_launch(data: LaunchInput, db: Session = Depends(get_db)):
        require(db, University, data.university_id)
        record = Launch(**data.model_dump(), stage=0)
        db.add(record)
        db.flush()
        db.add(StageEvent(launch_id=record.id, stage=0))
        db.commit()
        db.refresh(record)
        return serialize(record)

    @app.patch('/api/v1/launches/{id}', dependencies=[Depends(any_role)])
    def update_stage(id: int, data: StageInput, db: Session = Depends(get_db)):
        record = require(db, Launch, id)
        if record.stage != data.stage:
            record.stage = data.stage
            db.add(StageEvent(launch_id=id, stage=data.stage))
            db.commit()
        return serialize(record)

    @app.get('/api/v1/launches/{id}/history', dependencies=[Depends(any_role)])
    def history(id: int, db: Session = Depends(get_db)):
        require(db, Launch, id)
        return [serialize(x) for x in db.scalars(select(StageEvent).where(StageEvent.launch_id == id).order_by(StageEvent.id.desc()))]

    @app.get('/api/v1/tasks', dependencies=[Depends(any_role)])
    def tasks(db: Session = Depends(get_db)):
        return [serialize(x) for x in db.scalars(select(Task).order_by(Task.deadline, Task.id))]

    @app.patch('/api/v1/tasks/{id}', dependencies=[Depends(any_role)])
    def update_task(id: int, data: TaskInput, db: Session = Depends(get_db)):
        record = require(db, Task, id)
        record.done = data.done
        db.commit()
        return serialize(record)

    @app.get('/api/v1/dashboard', dependencies=[Depends(any_role)])
    def dashboard(db: Session = Depends(get_db)):
        rows = list(db.scalars(select(Launch)))
        return {'universities': len(list(db.scalars(select(University.id)))), 'launches': len(rows), 'students': sum(x.students for x in rows), 'overdue': sum(is_overdue(x) for x in rows), 'annual': [serialize(x) for x in db.scalars(select(AnnualMetric).order_by(AnnualMetric.year))]}

    return app
