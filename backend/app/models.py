from datetime import date, datetime, timezone
from sqlalchemy import ForeignKey, String, Date, DateTime, Boolean, MetaData
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
