from datetime import date, datetime, timezone
from sqlalchemy import ForeignKey, String, Date, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class University(Base):
    __tablename__ = 'universities'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(200), default='')

class Launch(Base):
    __tablename__ = 'launches'
    id: Mapped[int] = mapped_column(primary_key=True)
    university_id: Mapped[int] = mapped_column(ForeignKey('universities.id'))
    program: Mapped[str] = mapped_column(String(200))
    product: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str] = mapped_column(String(100))
    students: Mapped[int] = mapped_column(default=0)
    stage: Mapped[int] = mapped_column(default=0)
    deadline: Mapped[date] = mapped_column(Date)

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    launch_id: Mapped[int] = mapped_column(ForeignKey('launches.id'))
    title: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str] = mapped_column(String(100))
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
