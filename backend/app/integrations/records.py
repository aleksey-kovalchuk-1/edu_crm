"""The preliminary internal record format — an example, not the customer's contract."""
from datetime import timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSION = '0.1-preliminary'
Source = Literal['lms', 'website']


class InboundRecord(BaseModel):
    # extra='forbid': no arbitrary raw payload rides along with a record.
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    schema_version: Literal['0.1-preliminary'] = Field(description='Версия предварительного внутреннего формата')
    source: Source = Field(description='Система-источник: lms или website')
    external_id: str = Field(min_length=1, max_length=200, description='Идентификатор события в системе-источнике')
    occurred_at: AwareDatetime = Field(description='Время события с часовым поясом (ISO 8601)')
    event_type: str = Field(pattern=r'^[a-z][a-z0-9_.]{0,63}$',
                            description='Тип события; перечень определит контракт заказчика')
    university_ref: str = Field(min_length=1, max_length=200,
                                description='Ссылка на вуз в системе-источнике; сопоставление с каталогом CRM — после контракта')
    program_ref: str | None = Field(default=None, min_length=1, max_length=200,
                                    description='Ссылка на программу в системе-источнике (необязательно)')

    def normalized(self) -> dict:
        data = self.model_dump(mode='json')
        data['occurred_at'] = self.occurred_at.astimezone(timezone.utc).isoformat()
        return data
