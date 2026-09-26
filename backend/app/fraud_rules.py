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
    evidence_kind: str | None = None


def evaluate_application(existing, proposed_learner_id, course, stream_number, row_number):
    if (existing.learner_id == proposed_learner_id and existing.course == course
            and existing.stream_number == stream_number):
        return []
    return [FraudSignal('application_number_conflict', 1, 'high', 'course_application',
                        existing.id, proposed_learner_id, row_number)]


def evaluate_shared_contact(existing_learner_ids, incoming_learner_id, row_number=None):
    others = sorted(identifier for identifier in existing_learner_ids
                    if identifier > 0 and identifier != incoming_learner_id)
    if not others:
        return []
    primary = incoming_learner_id if incoming_learner_id and incoming_learner_id > 0 else others[0]
    related = others[0] if primary != others[0] else None
    return [FraudSignal('shared_contact', 1, 'medium', 'learner', primary, related, row_number)]


def evaluate_import_velocity(rows, recent_batch_count, row_limit=500, hourly_limit=10):
    if rows > row_limit or recent_batch_count > hourly_limit:
        return [FraudSignal('import_velocity', 1, 'medium', None, None, None, None)]
    return []


def evaluate_learner_match_conflict(candidate_ids, row_number):
    ids = sorted(identifier for identifier in candidate_ids if identifier > 0)
    return [FraudSignal('learner_match_conflict', 1, 'high', 'learner',
                        ids[0] if ids else None, ids[1] if len(ids) > 1 else None, row_number)]
