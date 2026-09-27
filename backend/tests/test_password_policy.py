import pytest

from app.password_policy import describe_policy


def test_the_realm_policy_in_russian():
    assert describe_policy('length(12) and notUsername and notEmail and passwordHistory(3)') == [
        'Не короче 12 символов', 'Не совпадает с логином', 'Не совпадает с email', 'Не повторяет последние 3 пароля',
    ]


@pytest.mark.parametrize('rule,text', [
    ('maxLength(64)', 'Не длиннее 64 символов'),
    ('digits(2)', 'Цифр — не меньше 2'),
    ('upperCase(1)', 'Заглавных букв — не меньше 1'),
    ('lowerCase(1)', 'Строчных букв — не меньше 1'),
    ('specialChars(1)', 'Спецсимволов — не меньше 1'),
    ('forceExpiredPasswordChange(90)', 'Меняется каждые 90 дней'),
    ('regexPattern(^a.*)', 'Правило Keycloak: regexPattern(^a.*)'),
])
def test_each_rule(rule, text):
    assert describe_policy(rule) == [text]


def test_empty_policy():
    assert describe_policy('') == []
