from fastapi.testclient import TestClient

from app.main import create_app


def test_swagger_ui_and_schema_are_served_under_api_prefix(database_url):
    # nginx proxies only /api/, so documentation must live under that prefix to be reachable on port 8080.
    with TestClient(create_app(database_url)) as client:
        docs = client.get('/api/docs')
        assert docs.status_code == 200
        assert 'swagger-ui' in docs.text.lower()

        schema = client.get('/api/openapi.json')
        assert schema.status_code == 200
        assert '/api/v1/launches' in schema.json()['paths']

        assert client.get('/docs').status_code == 404
