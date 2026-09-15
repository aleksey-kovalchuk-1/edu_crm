import pytest
from fastapi.routing import APIRoute

from app.auth import ALL_ROLES, current_auth
from helpers import login

PUBLIC_PATHS = {'/api/v1/health', '/api/v1/auth/login', '/api/v1/auth/callback'}
READ_ENDPOINTS = ['/api/v1/stages', '/api/v1/universities', '/api/v1/launches', '/api/v1/tasks', '/api/v1/dashboard']


def _dependency_calls(dependant):
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from _dependency_calls(dependency)


def test_every_api_route_declares_an_access_policy(app):
    unprotected = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in PUBLIC_PATHS:
            continue
        calls = list(_dependency_calls(route.dependant))
        if not any(call is current_auth or hasattr(call, 'allowed_roles') for call in calls):
            unprotected.append(f'{sorted(route.methods)} {route.path}')
    assert unprotected == []


def test_unauthenticated_reads_are_rejected(client):
    for path in READ_ENDPOINTS:
        assert client.get(path).status_code == 401, path


@pytest.mark.parametrize('role', ALL_ROLES)
def test_every_role_can_read(client, keycloak, role):
    login(client, keycloak, roles=(role,))
    for path in READ_ENDPOINTS:
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize('role, status', [('crm-user', 403), ('crm-supervisor', 201), ('crm-admin', 201)])
def test_only_heads_and_administrators_create_universities(client, keycloak, role, status):
    login(client, keycloak, roles=(role,))
    assert client.post('/api/v1/universities', json={'name': 'Вуз', 'city': 'Москва'}).status_code == status
