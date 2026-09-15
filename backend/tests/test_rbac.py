import pytest
from fastapi.routing import APIRoute

from app.auth import ALL_ROLES
from helpers import login

# Public endpoints are listed by method and path, so adding e.g. POST to a public path is still caught.
PUBLIC_ENDPOINTS = {
    ('GET', '/api/v1/health'),
    ('GET', '/api/v1/auth/login'),
    ('GET', '/api/v1/auth/callback'),
}
READ_ENDPOINTS = ['/api/v1/stages', '/api/v1/universities', '/api/v1/launches', '/api/v1/tasks', '/api/v1/dashboard', '/api/v1/audit/recent']


def _api_routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        # FastAPI 0.141 keeps included routers as wrapper objects in app.routes instead of copying their routes,
        # so the check must descend into them or it silently skips every router-mounted endpoint.
        included = getattr(route, 'original_router', None)
        if included is not None:
            yield from _api_routes(included.routes)


def _dependency_calls(dependant):
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from _dependency_calls(dependency)


def _is_access_check(call):
    return getattr(call, 'authenticates', False) or hasattr(call, 'allowed_roles')


def _endpoints(app):
    for route in _api_routes(app.routes):
        protected = any(_is_access_check(call) for call in _dependency_calls(route.dependant))
        for method in route.methods:
            yield method, route.path, protected


def test_route_discovery_includes_router_mounted_endpoints(app):
    paths = {path for _, path, _ in _endpoints(app)}
    assert {'/api/v1/auth/me', '/api/v1/auth/logout', '/api/v1/audit/recent', '/api/v1/launches'} <= paths


def test_every_api_route_declares_an_access_policy(app):
    unprotected = [f'{method} {path}' for method, path, protected in _endpoints(app)
                   if not protected and (method, path) not in PUBLIC_ENDPOINTS]
    assert unprotected == []


def test_public_endpoint_list_matches_reality(app):
    # A stale entry here would silently exempt a future route with the same method and path.
    public = {(method, path) for method, path, protected in _endpoints(app) if not protected}
    assert public == PUBLIC_ENDPOINTS


def test_non_api_routes_are_only_documentation_under_api_prefix(app):
    # Swagger UI and the schema are intentionally public (D-132) and must stay under the proxied /api prefix.
    others = {route.path for route in app.routes if not isinstance(route, APIRoute) and getattr(route, 'path', None)}
    assert others == {'/api/openapi.json', '/api/docs', '/api/docs/oauth2-redirect', '/api/redoc'}


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
