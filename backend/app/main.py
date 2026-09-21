from contextlib import asynccontextmanager
from datetime import date

import httpx
from fastapi import Depends, FastAPI, Request
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from .audit import record_event
from .audit_routes import router as audit_router
from .auth import ALL_ROLES, AuthContext, require_roles, router as auth_router
from .catalog_routes import active_university_in_scope, router as catalog_router, university_scope
from .import_routes import router as import_router
from .db import get_db
from .errors import AppError, ErrorCode, install_error_handlers
from .models import AnnualMetric, Launch, StageEvent, StatusChange, TaskPlanRun, TaskPlanTemplate, University, WorkflowStatus
from .plan_routes import resolve_assignee, run_generation, snapshot_template
from .plan_routes import router as plan_router
from .profile_routes import router as profile_router
from .task_routes import router as task_router
from .workflow_routes import router as workflow_router
from .workflows import active_statuses, all_statuses, default_template, launch_in_scope, status_at_position
from .oidc import OIDCClient
from .schemas import LaunchInput, StageInput
from .security import TokenCipher
from .settings import load_settings, validate_database_url
from .sms import send_sms

STAGES = ['Поиск контакта', 'Уточнение интереса', 'Встреча', 'Обмен документами', 'Согласование документов', 'Подписание', 'Передача материалов и лицензий', 'Внедрение продукта', 'Обучение преподавателей', 'Актуализация программы', 'Проведение занятий', 'Обновление материалов', 'Повышение квалификации']

any_role = require_roles(*ALL_ROLES)


def serialize(record):
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def is_overdue(launch):
    return launch.deadline < date.today() and launch.stage < 10


def generate_default_plan_for_launch(db, request, auth, university, launch):
    """Generates the one is_default_plan template's tasks for a newly created Interaction, exactly once.

    Never raises for a per-launch reason: any step whose assignee can't be resolved (no university
    manager, several of them, etc.) falls back to the Interaction's own creator, so this never blocks
    Interaction creation. Guarded against duplicate generation for the same launch_id.
    """
    already_generated = db.scalar(select(TaskPlanRun.id).where(TaskPlanRun.launch_id == launch.id))
    if already_generated is not None:
        return
    default_plan = db.scalar(select(TaskPlanTemplate).where(
        TaskPlanTemplate.is_default_plan.is_(True), TaskPlanTemplate.is_active.is_(True),
    ))
    if default_plan is None:
        return
    snapshot = snapshot_template(db, default_plan)
    overrides = {}
    for step in snapshot['steps']:
        assignee_id, issue = resolve_assignee(db, step, university.id, launch, auth.user.id)
        if assignee_id is None:
            overrides[str(step['id'])] = auth.user.id  # fall back to the Interaction's creator
    run_generation(db, request, auth.user, default_plan, snapshot, university.id, launch.id, date.today(), [], overrides)


def create_app(settings=None, *, http_client=None, sms_sender=None):
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
        swagger_ui_oauth2_redirect_url='/api/docs/oauth2-redirect',
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
    # Defaults to the real sender (log-only or HTTP, per settings.sms_provider_url — see app/sms.py);
    # tests substitute a fake here so phone verification tests assert on calls, not logs or real HTTP.
    app.state.sms_sender = sms_sender or send_sms
    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(audit_router)
    app.include_router(catalog_router)
    app.include_router(import_router)
    app.include_router(plan_router)
    app.include_router(profile_router)
    app.include_router(task_router)
    app.include_router(workflow_router)

    @app.get('/api/v1/health')
    def health(db: Session = Depends(get_db)):
        db.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.get('/api/v1/stages', dependencies=[Depends(any_role)])
    def stages(db: Session = Depends(get_db)):
        # Status names of the default workflow indexed by position, so renamed statuses show up in older screens.
        return [status.name for status in all_statuses(db, default_template(db).id)]

    @app.get('/api/v1/launches')
    def launches(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
        rows = db.execute(
            select(Launch, University).join(University)
            .where(university_scope(Launch.university_id, auth.user)).order_by(Launch.id)
        )
        return [{**serialize(l), 'university': u.name, 'city': u.city, 'overdue': is_overdue(l)} for l, u in rows]

    @app.post('/api/v1/launches', status_code=201)
    def add_launch(data: LaunchInput, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
        university = active_university_in_scope(db, auth.user, data.university_id)
        template = default_template(db)
        first_status = active_statuses(db, template.id)[0]
        record = Launch(**data.model_dump(), stage=first_status.position, workflow_template_id=template.id, status_id=first_status.id)
        db.add(record)
        db.flush()
        db.add(StageEvent(launch_id=record.id, stage=first_status.position))
        db.add(StatusChange(launch_id=record.id, from_status_id=None, to_status_id=first_status.id, user_id=auth.user.id))
        record_event(db, request, auth.user, 'launch.create', entity_type='launch', entity_id=record.id,
                     summary=f'Создано взаимодействие «{record.program}» с «{university.name}»',
                     payload={**data.model_dump(mode='json'), 'stage': first_status.position})
        generate_default_plan_for_launch(db, request, auth, university, record)
        db.commit()
        db.refresh(record)
        return serialize(record)

    @app.patch('/api/v1/launches/{id}')
    def update_stage(id: int, data: StageInput, request: Request, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
        record = launch_in_scope(db, auth.user, id)
        if record.stage != data.stage:
            status = status_at_position(db, record.workflow_template_id, data.stage)
            if status is None:
                raise AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': 'stage', 'message': 'В процессе нет активного статуса с таким номером', 'type': 'value_error'}])
            previous = record.stage
            previous_status = db.get(WorkflowStatus, record.status_id)
            db.add(StatusChange(launch_id=id, from_status_id=record.status_id, to_status_id=status.id, user_id=auth.user.id))
            record.stage = data.stage
            record.status_id = status.id
            db.add(StageEvent(launch_id=id, stage=data.stage))
            record_event(db, request, auth.user, 'launch.stage_change', entity_type='launch', entity_id=id,
                         summary=f'«{record.program}»: этап «{previous_status.name}» → «{status.name}»',
                         payload={'from': previous, 'to': data.stage})
            db.commit()
        return serialize(record)

    @app.get('/api/v1/launches/{id}/history')
    def history(id: int, auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
        launch_in_scope(db, auth.user, id)
        return [serialize(x) for x in db.scalars(select(StageEvent).where(StageEvent.launch_id == id).order_by(StageEvent.id.desc()))]

    @app.get('/api/v1/dashboard')
    def dashboard(auth: AuthContext = Depends(any_role), db: Session = Depends(get_db)):
        # Counts cover active universities in the user's scope; yearly statistics are company-wide (D-147).
        rows = list(db.scalars(
            select(Launch).join(University, University.id == Launch.university_id)
            .where(University.is_active.is_(True), university_scope(Launch.university_id, auth.user))
        ))
        universities = db.scalar(
            select(func.count()).select_from(University)
            .where(University.is_active.is_(True), university_scope(University.id, auth.user))
        )
        return {'universities': universities, 'launches': len(rows), 'students': sum(x.students for x in rows), 'overdue': sum(is_overdue(x) for x in rows), 'annual': [serialize(x) for x in db.scalars(select(AnnualMetric).order_by(AnnualMetric.year))]}

    return app
