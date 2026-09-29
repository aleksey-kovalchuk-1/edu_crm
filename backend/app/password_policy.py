"""Keycloak's password policy string, in Russian, for Настройки → Безопасность. Read-only: the policy is
changed only in Keycloak itself."""
import re

RULE_RE = re.compile(r'^(\w+)(?:\((.*)\))?$')
TEXTS = {
    'length': 'Не короче {} символов',
    'maxLength': 'Не длиннее {} символов',
    'notUsername': 'Не совпадает с логином',
    'notEmail': 'Не совпадает с email',
    # "Label: n" wording avoids Russian plural agreement ("3 пароля", "5 паролей", "1 день").
    'passwordHistory': 'Не совпадает с последними паролями: {}',
    'digits': 'Содержит цифр: не меньше {}',
    'upperCase': 'Содержит заглавных букв: не меньше {}',
    'lowerCase': 'Содержит строчных букв: не меньше {}',
    'specialChars': 'Содержит спецсимволов: не меньше {}',
    'forceExpiredPasswordChange': 'Срок действия пароля, дней: {}',
}


def describe_policy(policy: str) -> list[str]:
    lines = []
    for rule in filter(None, (part.strip() for part in (policy or '').split(' and '))):
        match = RULE_RE.match(rule)
        template = TEXTS.get(match.group(1)) if match else None
        if template and '{}' in template and match.group(2) is None:
            template = None  # e.g. a bare `length` with Keycloak's implicit default: don't print "None"
        # An unrecognised rule is shown as Keycloak wrote it rather than guessed at.
        lines.append(template.format(match.group(2)) if template else f'Правило сервиса входа: {rule}')
    return lines
