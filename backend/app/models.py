from datetime import date, datetime, timezone
from sqlalchemy import BigInteger, ForeignKey, Index, String, Date, DateTime, Boolean, MetaData, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Names match PostgreSQL's own defaults, so databases created before migrations existed keep identical constraint names.
NAMING_CONVENTION = {
    'ix': 'ix_%(column_0_label)s',
    'uq': '%(table_name)s_%(column_0_name)s_key',
    'ck': '%(table_name)s_%(constraint_name)s_check',
    'fk': '%(table_name)s_%(column_0_name)s_fkey',
    'pk': '%(table_name)s_pkey',
}

# ICU collation gives correct Russian ordering (е/ё, case) without re-initialising the database cluster.
RUSSIAN_COLLATION = 'ru-RU-x-icu'


def russian_text(length):
    return String(length, collation=RUSSIAN_COLLATION)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

class University(Base):
    __tablename__ = 'universities'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(russian_text(200))
    city: Mapped[str] = mapped_column(russian_text(100))
    contact: Mapped[str] = mapped_column(russian_text(200), default='')

class Launch(Base):
    __tablename__ = 'launches'
    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey('universities.id'))
    program: Mapped[str] = mapped_column(russian_text(200))
    product: Mapped[str] = mapped_column(russian_text(200))
    owner: Mapped[str] = mapped_column(russian_text(100))
    students: Mapped[int] = mapped_column(default=0)
    stage: Mapped[int] = mapped_column(default=0)
    deadline: Mapped[date] = mapped_column(Date)

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    launch_id: Mapped[int] = mapped_column(ForeignKey('launches.id'))
    title: Mapped[str] = mapped_column(russian_text(200))
    owner: Mapped[str] = mapped_column(russian_text(100))
    deadline: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

class StageEvent(Base):
    __tablename__ = 'stage_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    launch_id: Mapped[int] = mapped_column(ForeignKey('launches.id'))
    stage: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AnnualMetric(Base):
    __tablename__ = 'annual_metrics'
    year: Mapped[int] = mapped_column(primary_key=True)
    applications: Mapped[int]
    students: Mapped[int]
    streams: Mapped[int]


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    """Local mirror of a Keycloak account; Keycloak stays the source of identity and roles."""
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    keycloak_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(254), default='')
    full_name: Mapped[str] = mapped_column(russian_text(200))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = 'sessions'
    # SHA-256 of the cookie value; the raw token is never stored.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class LoginState(Base):
    """One pending browser login; stored in the database so any API worker can finish the callback."""
    __tablename__ = 'login_states'
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64))
    code_verifier: Mapped[str] = mapped_column(String(128))
    next_path: Mapped[str] = mapped_column(String(500))
    # SHA-256 of the edu_crm_login cookie: the callback must come from the browser that started the login.
    browser_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditEvent(Base):
    """Append-only record of a user action; the application never updates or deletes these rows."""
    __tablename__ = 'audit_events'
    __table_args__ = (Index('ix_audit_events_entity', 'entity_type', 'entity_id'),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(russian_text(300))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))
