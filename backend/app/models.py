from datetime import date, datetime, timezone
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, String, Date, DateTime, Boolean, MetaData, Table, Text, UniqueConstraint, false, true
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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
    name: Mapped[str] = mapped_column(russian_text(200), unique=True)
    city: Mapped[str] = mapped_column(russian_text(100))
    # Free-text contact from the first template; structured contacts live in university_contacts.
    contact: Mapped[str] = mapped_column(russian_text(200), default='')
    short_name: Mapped[str] = mapped_column(russian_text(100), default='', server_default='')
    region: Mapped[str] = mapped_column(russian_text(100), default='', server_default='')
    website: Mapped[str] = mapped_column(String(300), default='', server_default='')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Read-only view of assigned managers; assignments are changed through UniversityManager rows.
    managers: Mapped[list['User']] = relationship(
        'User',
        secondary='university_managers',
        primaryjoin='University.id == UniversityManager.university_id',
        secondaryjoin='User.id == UniversityManager.user_id',
        viewonly=True,
        order_by='User.full_name',
    )

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
    workflow_template_id: Mapped[int] = mapped_column(ForeignKey('workflow_templates.id'))
    status_id: Mapped[int] = mapped_column(ForeignKey('workflow_statuses.id'))

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


class WorkflowTemplate(Base):
    """A configurable interaction process (docs/design/workflows.md)."""
    __tablename__ = 'workflow_templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(russian_text(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    statuses: Mapped[list['WorkflowStatus']] = relationship(order_by='WorkflowStatus.position', viewonly=True)


class WorkflowStatus(Base):
    __tablename__ = 'workflow_statuses'
    __table_args__ = (UniqueConstraint('template_id', 'name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey('workflow_templates.id'), index=True)
    name: Mapped[str] = mapped_column(russian_text(120))
    position: Mapped[int]
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class StatusChange(Base):
    """One step in a launch's history: which status it moved to, who did it, with an optional comment and files."""
    __tablename__ = 'status_changes'
    id: Mapped[int] = mapped_column(primary_key=True)
    launch_id: Mapped[int] = mapped_column(ForeignKey('launches.id'), index=True)
    from_status_id: Mapped[int | None] = mapped_column(ForeignKey('workflow_statuses.id'))
    to_status_id: Mapped[int] = mapped_column(ForeignKey('workflow_statuses.id'))
    comment: Mapped[str] = mapped_column(Text, default='', server_default='')
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    attachments: Mapped[list['Attachment']] = relationship(order_by='Attachment.id', viewonly=True)


class Attachment(Base):
    """File metadata; the bytes live on the attachments volume under storage_key (D-153)."""
    __tablename__ = 'attachments'
    id: Mapped[int] = mapped_column(primary_key=True)
    status_change_id: Mapped[int] = mapped_column(ForeignKey('status_changes.id'), index=True)
    launch_id: Mapped[int] = mapped_column(ForeignKey('launches.id'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
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
    # CRM-owned phone verification (not Keycloak/OIDC, D-002 unaffected): phone lives here, not as a
    # Keycloak user attribute, because it is a CRM profile fact, not an identity fact Keycloak needs.
    phone: Mapped[str] = mapped_column(String(20), default='', server_default='')
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class PhoneVerificationCode(Base):
    """A one-time SMS code for CRM-owned phone verification; only the hash is stored (`app/phone.py`)."""
    __tablename__ = 'phone_verification_codes'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    # The number this code was sent to; kept alongside the code so a later edit to users.phone before this
    # code is verified can't be mistaken for what was actually sent.
    phone: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0, server_default='0')
    correlation_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


TRANSFER_STATUSES = ('not_started', 'in_progress', 'transferred', 'cancelled')

it_product_directions = Table(
    'it_product_directions',
    Base.metadata,
    Column('it_product_id', ForeignKey('it_products.id', ondelete='CASCADE'), primary_key=True),
    Column('it_direction_id', ForeignKey('it_directions.id'), primary_key=True),
)

contract_contacts = Table(
    'contract_contacts',
    Base.metadata,
    Column('contract_id', ForeignKey('contracts.id', ondelete='CASCADE'), primary_key=True),
    Column('university_contact_id', ForeignKey('university_contacts.id'), primary_key=True),
)


class ITDirection(Base):
    __tablename__ = 'it_directions'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(russian_text(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class ITProduct(Base):
    __tablename__ = 'it_products'
    __table_args__ = (UniqueConstraint('vendor', 'name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor: Mapped[str] = mapped_column(russian_text(200))
    # "Программное обеспечение" in the specification's import fields.
    name: Mapped[str] = mapped_column(russian_text(200))
    description: Mapped[str] = mapped_column(Text, default='', server_default='')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    directions: Mapped[list['ITDirection']] = relationship(secondary=it_product_directions, order_by='ITDirection.name')


class UniversityContact(Base):
    """Responsible person on the university side; personal data, visible only within the user's data scope."""
    __tablename__ = 'university_contacts'
    __table_args__ = (UniqueConstraint('university_id', 'full_name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey('universities.id'), index=True)
    full_name: Mapped[str] = mapped_column(russian_text(200))
    position: Mapped[str] = mapped_column(russian_text(200), default='', server_default='')
    email: Mapped[str] = mapped_column(String(254), default='', server_default='')
    phone: Mapped[str] = mapped_column(String(50), default='', server_default='')
    comment: Mapped[str] = mapped_column(Text, default='', server_default='')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class UniversityManager(Base):
    """A CRM user responsible for a university; defines a manager's data scope (D-141)."""
    __tablename__ = 'university_managers'
    university_id: Mapped[int] = mapped_column(ForeignKey('universities.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    assigned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))


class Contract(Base):
    """A licence contract for an IT product at a university (the specification's import fields)."""
    __tablename__ = 'contracts'
    __table_args__ = (
        CheckConstraint('valid_until >= signed_at', name='valid_period'),
        CheckConstraint(f"transfer_status in ({', '.join(repr(s) for s in TRANSFER_STATUSES)})", name='transfer_status'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_number: Mapped[str] = mapped_column(String(100), unique=True)
    university_id: Mapped[int] = mapped_column(ForeignKey('universities.id'), index=True)
    it_product_id: Mapped[int] = mapped_column(ForeignKey('it_products.id'), index=True)
    signed_at: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    transfer_status: Mapped[str] = mapped_column(String(20), default='not_started', server_default='not_started')
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    # Manager name as imported when it could not be matched to exactly one CRM user (D-140).
    manager_name: Mapped[str] = mapped_column(russian_text(200), default='', server_default='')
    comment: Mapped[str] = mapped_column(Text, default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    contacts: Mapped[list['UniversityContact']] = relationship(secondary=contract_contacts, order_by='UniversityContact.full_name')
    university: Mapped['University'] = relationship()
    it_product: Mapped['ITProduct'] = relationship()
    manager: Mapped['User | None'] = relationship(foreign_keys=[manager_user_id])


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


IMPORT_STATUSES = ('uploaded', 'applied')


class CatalogImport(Base):
    """An uploaded catalog file: parsed rows, the mapping used and the apply report; the file itself is not kept."""
    __tablename__ = 'catalog_imports'
    __table_args__ = (
        CheckConstraint(f"status in ({', '.join(repr(s) for s in IMPORT_STATUSES)})", name='status'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    header_row: Mapped[int]
    headers: Mapped[list] = mapped_column(JSONB)
    # [[row number, [cell, ...]], ...]; dates are stored as {"$date": "YYYY-MM-DD"}.
    rows: Mapped[list] = mapped_column(JSONB)
    suggested_mapping: Mapped[dict] = mapped_column(JSONB)
    mapping: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default='uploaded')
    report: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
