"""The sign-in pages' configuration stays consistent across the realm file, the theme folder and compose.yaml."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / 'deploy/keycloak/themes/edu-crm/login'


def _realm():
    return json.loads((ROOT / 'deploy/keycloak/realm-edu-crm.json').read_text())


def _email_rule():
    provider = _realm()['components']['org.keycloak.userprofile.UserProfileProvider'][0]
    profile = json.loads(provider['config']['kc.user.profile.config'][0])
    return next(a for a in profile['attributes'] if a['name'] == 'email')['validations']['pattern']


def test_new_installations_use_the_unicrm_theme():
    assert _realm()['loginTheme'] == 'edu-crm'
    assert 'parent=keycloak.v2' in (THEME / 'theme.properties').read_text()
    assert './deploy/keycloak/themes/edu-crm:/opt/keycloak/themes/edu-crm:ro' in (ROOT / 'compose.yaml').read_text()


def test_the_ru_rule_shows_a_sentence_not_a_message_key():
    rule = _email_rule()
    assert re.fullmatch(rule['pattern'], 'ivanov@mail.ru')
    assert re.fullmatch(rule['pattern'], 'Ivanov@Mail.RU')
    assert not re.fullmatch(rule['pattern'], 'ivanov@example.com')
    assert not re.fullmatch(rule['pattern'], 'ivanov@mail.ru.com')
    assert ' ' in rule['error-message'] and '.ru' in rule['error-message']


def test_realms_that_still_use_the_old_key_get_the_same_sentence():
    messages = (THEME / 'messages/messages_ru.properties').read_text()
    assert 'emailRuOnly=' + _email_rule()['error-message'] in messages


def test_the_script_and_the_realm_file_agree():
    script = (ROOT / 'scripts/keycloak-login-settings.sh').read_text()
    rule = _email_rule()
    assert f"PATTERN='{rule['pattern']}'" in script
    assert f"MESSAGE='{rule['error-message']}'" in script


def test_every_script_and_style_the_theme_lists_exists():
    properties = dict(line.split('=', 1) for line in (THEME / 'theme.properties').read_text().splitlines()
                      if '=' in line and not line.startswith('#'))
    own = [name for name in properties['styles'].split() if name != 'css/styles.css'] + properties['scripts'].split()
    missing = [name for name in own if not (THEME / 'resources' / name).is_file()]
    assert missing == []
