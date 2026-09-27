"""Scoped interaction analytics; one snapshot is shared by JSON and PDF output."""

from collections import defaultdict
from datetime import date
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from .analytics_metrics import first_implementation_at, funnel_counts, monthly_implementations, top_universities
from .analytics_pdf import build_analytics_pdf, date_label
from .auth import ALL_ROLES, AuthContext, require_roles
from .catalog_routes import university_scope
from .db import get_db
from .errors import AppError, ErrorCode
from .models import Launch, StatusChange, University, WorkflowStatus
from .workflows import stage_group

router = APIRouter(prefix='/api/v1/analytics', tags=['Аналитика'])
any_role = require_roles(*ALL_ROLES)
MAX_ANALYTICS_MONTHS = 120


def validation_error(field: str, message: str) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, details=[{'field': field, 'message': message, 'type': 'value_error'}])


def analytics_snapshot(
    db: Session, user, period_from: date, period_to: date,
    university_ids: list[int], time_zone_name: str,
) -> dict:
    if period_from > period_to:
        raise validation_error('period_to', 'Конец периода раньше начала')
    month_count = (period_to.year - period_from.year) * 12 + period_to.month - period_from.month + 1
    if month_count > MAX_ANALYTICS_MONTHS:
        raise validation_error('period_to', 'Период не может превышать 10 лет')
    try:
        time_zone = ZoneInfo(time_zone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise validation_error('time_zone', 'Неизвестный часовой пояс') from error

    accessible = list(db.scalars(
        select(University).where(
            University.is_active.is_(True), university_scope(University.id, user),
        ).order_by(University.name)
    ))
    by_id = {university.id: university for university in accessible}
    if set(university_ids) - by_id.keys():
        raise AppError(ErrorCode.RECORD_NOT_FOUND)
    selected = [by_id[id] for id in dict.fromkeys(university_ids)] if university_ids else accessible
    selected_ids = [university.id for university in selected]
    launches = list(db.scalars(select(Launch).where(Launch.university_id.in_(selected_ids))))
    launches_by_id = {launch.id: launch for launch in launches}

    changes_by_launch = defaultdict(list)
    reached = []
    if launches_by_id:
        previous = aliased(WorkflowStatus)
        current = aliased(WorkflowStatus)
        changes = db.execute(
            select(StatusChange.launch_id, StatusChange.from_status_id, StatusChange.to_status_id,
                   previous.position, current.position, StatusChange.created_at)
            .outerjoin(previous, previous.id == StatusChange.from_status_id)
            .join(current, current.id == StatusChange.to_status_id)
            .where(StatusChange.launch_id.in_(launches_by_id))
            .order_by(StatusChange.created_at, StatusChange.id)
        )
        for launch_id, from_id, to_id, previous_position, current_position, changed_at in changes:
            changes_by_launch[launch_id].append((previous_position, current_position, changed_at))
            if from_id != to_id and period_from <= changed_at.astimezone(time_zone).date() <= period_to:
                reached.append((launches_by_id[launch_id].university_id, stage_group(current_position)))

    implementations = []
    implemented_rows = []
    for launch_id, changes in changes_by_launch.items():
        implemented_at = first_implementation_at(changes)
        if implemented_at is not None and period_from <= implemented_at.astimezone(time_zone).date() <= period_to:
            launch = launches_by_id[launch_id]
            implementations.append(implemented_at)
            implemented_rows.append((launch.university_id, by_id[launch.university_id].name, launch.students))

    return {
        'period_from': period_from.isoformat(),
        'period_to': period_to.isoformat(),
        'time_zone': time_zone_name,
        'universities': [university.name for university in selected] if university_ids else ['Все вузы'],
        'stages': funnel_counts(reached),
        'monthly': monthly_implementations(implementations, period_from, period_to, time_zone),
        'ranking': top_universities(implemented_rows),
        'has_stage_data': bool(reached),
        'has_implementation_data': bool(implementations),
    }


@router.get('/interactions', summary='Аналитика взаимодействий с вузами')
def interaction_analytics(
    period_from: date,
    period_to: date,
    time_zone: str = Query(min_length=1, max_length=100),
    university_id: list[int] = Query(default=[]),
    auth: AuthContext = Depends(any_role), db: Session = Depends(get_db),
):
    return analytics_snapshot(db, auth.user, period_from, period_to, university_id, time_zone)


@router.get('/interactions.pdf', summary='PDF аналитики взаимодействий')
def interaction_analytics_pdf(
    period_from: date,
    period_to: date,
    time_zone: str = Query(min_length=1, max_length=100),
    university_id: list[int] = Query(default=[]),
    auth: AuthContext = Depends(any_role), db: Session = Depends(get_db),
):
    snapshot = analytics_snapshot(db, auth.user, period_from, period_to, university_id, time_zone)
    filename = f'Аналитика_UniCRM_{date_label(snapshot["period_from"])}-{date_label(snapshot["period_to"])}.pdf'
    return Response(
        content=build_analytics_pdf(snapshot), media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="Analytics_UniCRM.pdf"; filename*=UTF-8\'\'{quote(filename)}',
            'Cache-Control': 'no-store',
        },
    )
