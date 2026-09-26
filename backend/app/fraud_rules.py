"""Deterministic review signals with identifiers only, never source values."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FraudSignal:
    rule_code: str
    rule_version: int
    priority: str
    entity_type: str | None
    entity_id: int | None
    related_entity_id: int | None
    row_number: int | None


def evaluate_application(existing, proposed_learner_id, course, stream_number, row_number):
    if (existing.learner_id == proposed_learner_id and existing.course == course
            and existing.stream_number == stream_number):
        return []
    return [FraudSignal('application_number_conflict', 1, 'high', 'course_application',
                        existing.id, proposed_learner_id, row_number)]
