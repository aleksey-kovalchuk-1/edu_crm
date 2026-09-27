"""Reads a Keycloak user-profile JSON on stdin; prints it with "middleName" added, or "unchanged"."""
import json
import sys

MIDDLE_NAME = {
    'name': 'middleName',
    'displayName': 'Отчество',
    'validations': {'length': {'max': 100}},
    'permissions': {'view': ['admin', 'user'], 'edit': ['admin']},
    'multivalued': False,
}


def add_middle_name(profile):
    attributes = profile.setdefault('attributes', [])
    if any(a.get('name') == 'middleName' for a in attributes):
        return None
    last_name_at = next((i for i, a in enumerate(attributes) if a.get('name') == 'lastName'), len(attributes) - 1)
    attributes.insert(last_name_at + 1, dict(MIDDLE_NAME))
    return profile


if __name__ == '__main__':
    result = add_middle_name(json.load(sys.stdin))
    print('unchanged' if result is None else json.dumps(result, ensure_ascii=False))
