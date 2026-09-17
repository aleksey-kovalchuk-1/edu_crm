"""Mock LMS/website-CMS connector framework (T-060, D-184-D-187).

Real contracts were not available, so this is a documented **mock**: `docs/api/integrations.md` is the
contract, `CONNECTOR_SOURCES` (`app/models.py`) lists the two mock sources (`lms`, `cms`). Both share one
framework because the shape of "sync one external interaction into/out of the CRM" is identical for both;
a real integration would very likely need its own request/response shape, which is exactly why the two
layers below are kept separate:

- `apply_interaction` (this module): operates on already-resolved CRM entities (`University`,
  `WorkflowStatus`, a `Launch`) and knows nothing about JSON, HTTP, or any wire format.
- `app/connector_routes.py`: parses one connector's wire payload, resolves its human-readable references
  (university name, status name) into the CRM entities `apply_interaction` needs, and turns the result back
  into that connector's response shape.

Swapping the mock for a real contract means rewriting the route layer's parsing/resolution and response
shaping; `apply_interaction`'s idempotent create-or-update logic does not change.
"""
from dataclasses import dataclass

from sqlalchemy import select

from .models import IntegrationLink, Launch, StageEvent, StatusChange, University, WorkflowStatus, WorkflowTemplate
from .workflows import active_statuses, default_template

UPDATABLE_FIELDS = ('program', 'product', 'responsible', 'students', 'deadline')


class ConnectorValidationError(Exception):
    """Raised with one or more `{field, message}` problems; the route layer turns this into a 422."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__('; '.join(p['message'] for p in self.problems))


@dataclass
class ResolvedInteraction:
    """Wire fields already translated into CRM entities/values by the route layer -- see the module
    docstring. `None` on an updatable field means "the delivery did not include it, leave it unchanged";
    only meaningful on an update (a create requires every field the CRM's `Launch` itself requires)."""
    university: University | None
    status: WorkflowStatus | None
    program: str | None
    product: str | None
    responsible: str | None
    students: int | None
    deadline: object | None  # datetime.date | None


def find_link(db, source, external_id):
    return db.scalar(select(IntegrationLink).where(IntegrationLink.source == source, IntegrationLink.external_id == external_id))


def _create_launch(db, resolved):
    missing = [field for field in ('university', 'program', 'product', 'responsible', 'deadline')
               if getattr(resolved, field) is None]
    if missing:
        raise ConnectorValidationError(
            {'field': field, 'message': f'Обязательное поле для создания взаимодействия: {field}'} for field in missing
        )
    template = default_template(db)
    status = resolved.status or active_statuses(db, template.id)[0]
    launch = Launch(
        university_id=resolved.university.id, program=resolved.program, product=resolved.product,
        owner=resolved.responsible, students=resolved.students or 0, deadline=resolved.deadline,
        stage=status.position, workflow_template_id=template.id, status_id=status.id,
    )
    db.add(launch)
    db.flush()
    db.add(StageEvent(launch_id=launch.id, stage=status.position))
    db.add(StatusChange(launch_id=launch.id, from_status_id=None, to_status_id=status.id, user_id=None))
    return launch, True


def _update_launch(db, launch, resolved):
    changed = False
    for field in ('program', 'product', 'students', 'deadline'):
        value = getattr(resolved, field)
        if value is not None and getattr(launch, field) != value:
            setattr(launch, field, value)
            changed = True
    if resolved.responsible is not None and launch.owner != resolved.responsible:
        launch.owner = resolved.responsible
        changed = True
    if resolved.status is not None and resolved.status.id != launch.status_id:
        db.add(StatusChange(launch_id=launch.id, from_status_id=launch.status_id, to_status_id=resolved.status.id, user_id=None))
        db.add(StageEvent(launch_id=launch.id, stage=resolved.status.position))
        launch.status_id = resolved.status.id
        launch.stage = resolved.status.position
        changed = True
    return launch, changed


def apply_interaction(db, source, external_id, resolved):
    """Idempotent create-or-update: `(source, external_id)` is the only identity a repeated delivery is
    matched against (T-060). Returns `(launch, link, action)` where `action` is `'created'`, `'updated'`
    or `'unchanged'` -- never raises for a second identical delivery."""
    link = find_link(db, source, external_id)
    if link is None:
        launch, _ = _create_launch(db, resolved)
        link = IntegrationLink(source=source, external_id=external_id, launch_id=launch.id)
        db.add(link)
        return launch, link, 'created'
    launch = db.get(Launch, link.launch_id)
    launch, changed = _update_launch(db, launch, resolved)
    return launch, link, ('updated' if changed else 'unchanged')


def outbound_state(db, launch, link):
    """The CRM's current state of one interaction, in the shape a connector's outbound feed returns."""
    university = db.get(University, launch.university_id)
    status = db.get(WorkflowStatus, launch.status_id)
    template = db.get(WorkflowTemplate, launch.workflow_template_id)
    return {
        'crm_id': launch.id,
        'external_id': link.external_id if link else None,
        'university': university.name if university else None,
        'program': launch.program,
        'product': launch.product,
        'workflow': template.name if template else None,
        'status': status.name if status else None,
        'responsible': launch.owner,
        'students': launch.students,
        'deadline': launch.deadline,
        'updated_at': link.updated_at if link else None,
    }
