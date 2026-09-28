import pytest

from app.password_policy import describe_policy


def test_the_realm_policy_in_russian():
    assert describe_policy('length(12) and notUsername and notEmail and passwordHistory(3)') == [
        'Не короче 12 символов', 'Не совпадает с логином', 'Не совпадает с email', 'Не совпадает с последними паролями: 3',
    ]


@pytest.mark.parametrize('rule,text', [
    ('maxLength(64)', 'Не длиннее 64 символов'),
    ('digits(2)', 'Содержит цифр: не меньше 2'),
    ('upperCase(1)', 'Содержит заглавных букв: не меньше 1'),
    ('lowerCase(1)', 'Содержит строчных букв: не меньше 1'),
    ('specialChars(1)', 'Содержит спецсимволов: не меньше 1'),
    ('forceExpiredPasswordChange(1)', 'Срок действия пароля, дней: 1'),
    ('passwordHistory(5)', 'Не совпадает с последними паролями: 5'),
    ('length', 'Правило Keycloak: length'),
    ('regexPattern(^a.*)', 'Правило Keycloak: regexPattern(^a.*)'),
])
def test_each_rule(rule, text):
    assert describe_policy(rule) == [text]


def test_empty_policy():
    assert describe_policy('') == []
