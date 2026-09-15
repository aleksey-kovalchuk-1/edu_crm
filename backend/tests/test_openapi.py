def test_swagger_ui_and_schema_are_served_under_api_prefix(client):
    # nginx proxies only /api/, so documentation must live under that prefix to be reachable on port 8080.
    docs = client.get('/api/docs')
    assert docs.status_code == 200
    assert 'swagger-ui' in docs.text.lower()

    schema = client.get('/api/openapi.json')
    assert schema.status_code == 200
    paths = schema.json()['paths']
    assert '/api/v1/launches' in paths
    assert '/api/v1/auth/login' in paths

    assert client.get('/docs').status_code == 404
