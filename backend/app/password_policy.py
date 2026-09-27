"""Keycloak's password policy string, in Russian, for Настройки → Безопасность. Read-only: the policy is
changed only in Keycloak itself."""
import re

RULE_RE = re.compile(r'^(\w+)(?:\((.*)\))?$')
TEXTS = {
    'length': 'Не короче {} символов',
    'maxLength': 'Не длиннее {} символов',
    'notUsername': 'Не совпадает с логином',
    'notEmail': 'Не совпадает с email',
    'passwordHistory': 'Не повторяет последние {} пароля',
    'digits': 'Цифр — не меньше {}',
    'upperCase': 'Заглавных букв — не меньше {}',
    'lowerCase': 'Строчных букв — не меньше {}',
    'specialChars': 'Спецсимволов — не меньше {}',
    'forceExpiredPasswordChange': 'Меняется каждые {} дней',
}


def describe_policy(policy: str) -> list[str]:
    lines = []
    for rule in filter(None, (part.strip() for part in (policy or '').split(' and '))):
        match = RULE_RE.match(rule)
        template = TEXTS.get(match.group(1)) if match else None
        # An unrecognised rule is shown as Keycloak wrote it rather than guessed at.
        lines.append(template.format(match.group(2)) if template else f'Правило Keycloak: {rule}')
    return lines
