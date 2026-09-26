from types import SimpleNamespace

from app.fraud_rules import evaluate_application


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
