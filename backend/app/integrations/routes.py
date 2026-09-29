"""Swagger-visible description of the preliminary boundary and POST placeholders (D-246).

Nothing here is the customer's API contract. The placeholders check a record against the internal format and store
nothing: no rows, no raw payload, no workflow, report or analytics effect.
"""
from fastapi import APIRouter, Depends

from ..auth import ROLE_ADMIN, require_roles
from ..errors import AppError, ErrorCode
from .adapters import PreliminaryLmsAdapter, PreliminaryWebsiteAdapter
from .records import SCHEMA_VERSION, InboundRecord

router = APIRouter(prefix='/api/v1/integrations', tags=['Интеграции LMS и сайта (предварительно)'])
# crm-superadmin is a composite that includes crm-admin, so it passes too.
admin_only = require_roles(ROLE_ADMIN)

NOTICE = ('Внутренний пример, не контракт заказчика. Формат предварительный: контракты и образцы данных LMS и сайта '
          'ИТ Школы ещё не получены. Данные не сохраняются и не используются в процессах, отчётах и аналитике.')
ADAPTERS = {'lms': PreliminaryLmsAdapter(), 'website': PreliminaryWebsiteAdapter()}
EXAMPLES = {
    'lms': [{
        'preliminary': True,
        'title': 'Пример: зачисление на программу (предварительно)',
        'record': {
            'schema_version': SCHEMA_VERSION, 'source': 'lms', 'external_id': 'lms-example-0001',
            'occurred_at': '2026-09-29T09:30:00+03:00', 'event_type': 'enrollment',
            'university_ref': 'example-university', 'program_ref': 'example-program',
        },
    }],
    'website': [{
        'preliminary': True,
        'title': 'Пример: заявка с сайта (предварительно)',
        'record': {
            'schema_version': SCHEMA_VERSION, 'source': 'website', 'external_id': 'site-example-0001',
            'occurred_at': '2026-09-29T10:15:00+03:00', 'event_type': 'application',
            'university_ref': 'example-university', 'program_ref': None,
        },
    }],
}


@router.get('/contracts', summary='Предварительный формат обмена с LMS и сайтом (внутренний пример)',
            description=NOTICE, dependencies=[Depends(admin_only)])
def contracts():
    return {
        'preliminary': True,
        'customer_contract': False,
        'notice': NOTICE,
        'schema_version': SCHEMA_VERSION,
        'stores_data': False,
        'record_schema': InboundRecord.model_json_schema(),
        'sources': {
            source: {
                'status': 'awaiting_customer_contract',
                'endpoint': f'/api/v1/integrations/{source}',
                'examples': examples,
            }
            for source, examples in EXAMPLES.items()
        },
    }


def _check(source: str, record: InboundRecord):
    try:
        checked = ADAPTERS[source].parse(record.model_dump())
    except ValueError as error:
        raise AppError(ErrorCode.VALIDATION_ERROR, str(error)) from None
    return {
        'status': 'validated_only',
        'stored': False,
        'preliminary': True,
        'message': 'Запись соответствует предварительному внутреннему формату и не сохранена: '
                   'контракт заказчика ещё не утверждён.',
        'record': checked.normalized(),
    }


PLACEHOLDER = NOTICE + ' Заглушка: проверяет запись и ничего не сохраняет.'


@router.post('/lms', summary='Заглушка приёма записи LMS (только проверка формата)',
             description=PLACEHOLDER, dependencies=[Depends(admin_only)])
def receive_lms(record: InboundRecord):
    return _check('lms', record)


@router.post('/website', summary='Заглушка приёма записи сайта (только проверка формата)',
             description=PLACEHOLDER, dependencies=[Depends(admin_only)])
def receive_website(record: InboundRecord):
    return _check('website', record)
