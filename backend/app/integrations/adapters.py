"""Adapter interfaces for the LMS and the website. The preliminary implementations only check the internal format."""
from typing import Protocol, runtime_checkable

from .records import InboundRecord


@runtime_checkable
class LmsAdapter(Protocol):
    def parse(self, payload: dict) -> InboundRecord: ...


@runtime_checkable
class WebsiteAdapter(Protocol):
    def parse(self, payload: dict) -> InboundRecord: ...


class _PreliminaryAdapter:
    source: str

    def parse(self, payload: dict) -> InboundRecord:
        record = InboundRecord.model_validate(payload)
        if record.source != self.source:
            raise ValueError(f'Запись для источника «{record.source}», ожидается «{self.source}»')
        return record


class PreliminaryLmsAdapter(_PreliminaryAdapter):
    source = 'lms'


class PreliminaryWebsiteAdapter(_PreliminaryAdapter):
    source = 'website'
