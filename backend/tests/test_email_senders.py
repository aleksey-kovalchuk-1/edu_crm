from helpers import login


def test_only_supervisor_and_admin_can_create_a_sender_identity(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders', json={
        'email_address': 'info@unicrm.tech', 'display_name': 'UniCRM — общая почта',
    })
    assert response.status_code == 403


def test_supervisor_can_create_and_it_is_immediately_approved(client, keycloak):
    login(client, keycloak, roles=('crm-supervisor',))
    response = client.post('/api/v1/email-senders', json={
        'email_address': 'info@unicrm.tech', 'display_name': 'UniCRM — общая почта',
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body['email_address'] == 'info@unicrm.tech'
    assert body['is_active'] is True


def test_rejects_an_invalid_email_address(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    response = client.post('/api/v1/email-senders', json={
        'email_address': 'not-an-email', 'display_name': 'Тест',
    })
    assert response.status_code == 422


def test_any_signed_in_user_can_list_active_senders(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    client.post('/api/v1/email-senders', json={'email_address': 'info@unicrm.tech', 'display_name': 'Общая почта'})
    login(client, keycloak, roles=('crm-user',))
    response = client.get('/api/v1/email-senders')
    assert response.status_code == 200
    assert any(s['email_address'] == 'info@unicrm.tech' for s in response.json())


def test_deactivating_removes_it_from_the_selectable_list(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    created = client.post('/api/v1/email-senders', json={'email_address': 'info@unicrm.tech', 'display_name': 'Общая почта'}).json()
    response = client.delete(f"/api/v1/email-senders/{created['id']}")
    assert response.status_code == 204
    listing = client.get('/api/v1/email-senders').json()
    assert not any(s['id'] == created['id'] for s in listing)


def test_only_supervisor_and_admin_can_deactivate(client, keycloak):
    login(client, keycloak, roles=('crm-admin',))
    created = client.post('/api/v1/email-senders', json={'email_address': 'info@unicrm.tech', 'display_name': 'Общая почта'}).json()
    login(client, keycloak, roles=('crm-user',))
    response = client.delete(f"/api/v1/email-senders/{created['id']}")
    assert response.status_code == 403


def test_test_send_reports_logged_only_when_no_provider_configured(client, keycloak):
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['delivered'] is False
    assert 'не настроен' in body['message'].lower() or 'журнал' in body['message'].lower()


def test_test_send_uses_the_callers_own_email_never_a_supplied_address(client, keycloak, app):
    sent = []
    app.state.email_sender = lambda settings, to, subject, body: sent.append((to, subject, body))
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 200
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == 'anna.demo@demo.local'  # matches this fixture's default logged-in user's email — confirm the real value against helpers.py/fake_keycloak.py rather than assuming


def test_test_send_reports_delivered_true_when_a_sender_is_injected(client, keycloak, app):
    app.state.email_sender = lambda settings, to, subject, body: None
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.json()['delivered'] is True


def test_test_send_surfaces_a_send_failure_as_a_service_error(client, keycloak, app):
    from app.email import EmailSendError

    def failing_sender(settings, to, subject, body):
        raise EmailSendError('provider down')

    app.state.email_sender = failing_sender
    login(client, keycloak, roles=('crm-user',))
    response = client.post('/api/v1/email-senders/test')
    assert response.status_code == 503
