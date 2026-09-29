"""Security headers on the web container (T-070).

The CRM pages get a report-only CSP first (it logs violations, blocks nothing); Keycloak pages under /auth keep
their own headers — a site-wide CSP would block the login page's scripts and reCAPTCHA. HSTS only makes sense on the
public HTTPS deployment.
"""
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'
LOCAL = (FRONTEND / 'nginx.conf').read_text()
PUBLIC = (FRONTEND / 'nginx.public.conf').read_text()


def _block(conf, header):
    """The text of the location block that starts with `header`."""
    start = conf.index(header)
    depth = 0
    for index in range(conf.index('{', start), len(conf)):
        depth += {'{': 1, '}': -1}.get(conf[index], 0)
        if depth == 0:
            return conf[start:index + 1]
    raise AssertionError(header)


def _server_level(conf):
    server = _block(conf, 'server {')
    # Only real directives (a line starting with `location`), not the word inside a comment.
    return re.sub(r'(?m)^\s*location [^{\n]*\{[^{}]*(\{[^{}]*\}[^{}]*)*\}', '', server)


@pytest.mark.parametrize('conf', [LOCAL, PUBLIC], ids=['local', 'public'])
def test_every_response_gets_the_basic_headers(conf):
    server = _server_level(conf)
    assert 'add_header X-Content-Type-Options nosniff always;' in server
    assert "add_header Referrer-Policy strict-origin-when-cross-origin always;" in server
    assert 'add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;' in server


@pytest.mark.parametrize('conf', [LOCAL, PUBLIC], ids=['local', 'public'])
def test_the_crm_pages_get_a_report_only_csp_and_keep_the_basic_headers(conf):
    app = _block(conf, 'location / {')
    assert 'Content-Security-Policy-Report-Only' in app
    policy = re.search(r'Content-Security-Policy-Report-Only "([^"]+)"', app).group(1)
    assert "default-src 'self'" in policy and "frame-ancestors 'self'" in policy and "object-src 'none'" in policy
    # add_header inside a location replaces the server-level ones, so they are repeated here.
    for header in ('X-Content-Type-Options', 'Referrer-Policy', 'Permissions-Policy'):
        assert f'add_header {header}' in app


@pytest.mark.parametrize('conf', [LOCAL, PUBLIC], ids=['local', 'public'])
def test_keycloak_and_the_api_get_no_csp_from_nginx(conf):
    assert 'Content-Security-Policy' not in _server_level(conf)
    assert 'Content-Security-Policy' not in _block(conf, 'location /auth/ {')
    assert 'Content-Security-Policy' not in _block(conf, 'location /api/ {')


def test_hsts_is_sent_only_by_the_public_https_deployment():
    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in _server_level(PUBLIC)
    assert 'Strict-Transport-Security' in _block(PUBLIC, 'location / {')
    assert 'Strict-Transport-Security' not in LOCAL


def test_the_two_configs_differ_only_in_the_forwarded_scheme_and_hsts():
    def normalized(conf):
        body = conf[conf.index('limit_req_zone'):]
        body = re.sub(r'proxy_set_header X-Forwarded-Proto \S+;', 'proxy_set_header X-Forwarded-Proto <scheme>;', body)
        return [line.strip() for line in body.splitlines() if line.strip() and 'Strict-Transport-Security' not in line]
    assert normalized(LOCAL) == normalized(PUBLIC)
