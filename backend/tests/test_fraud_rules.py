from types import SimpleNamespace

from app.fraud_rules import evaluate_application, evaluate_import_velocity, evaluate_shared_contact


def test_application_number_conflict_uses_only_safe_metadata():
    existing = SimpleNamespace(id=4, learner_id=7, course='Python', stream_number='P1')
    assert evaluate_application(existing, 7, 'Python', 'P1', 2) == []
    changed_course = evaluate_application(existing, 7, 'Другой курс', 'P1', 2)
    assert [signal.rule_code for signal in changed_course] == ['application_number_conflict']
    assert changed_course[0].priority == 'high'
    assert changed_course[0].entity_id == 4
    changed_person = evaluate_application(existing, 8, 'Python', 'P1', 2)
    assert [signal.rule_code for signal in changed_person] == ['application_number_conflict']
    assert 'Другой курс' not in repr(changed_course)


def test_shared_contact_is_warning_for_distinct_profiles():
    signals = evaluate_shared_contact({1, 2}, incoming_learner_id=2)
    assert [signal.rule_code for signal in signals] == ['shared_contact']
    assert signals[0].priority == 'medium'
    assert evaluate_shared_contact({2}, incoming_learner_id=2) == []


def test_import_velocity_uses_documented_thresholds():
    assert evaluate_import_velocity(rows=500, recent_batch_count=10) == []
    assert evaluate_import_velocity(rows=501, recent_batch_count=0)[0].rule_code == 'import_velocity'
    assert evaluate_import_velocity(rows=1, recent_batch_count=11)[0].rule_code == 'import_velocity'
