import httpx
import pytest

from app.email import EmailSendError, send_email


def make_settings(**overrides):
    from helpers import make_settings as base_make_settings
    return base_make_settings('postgresql+psycopg://u:p@h:5432/db', **overrides)


def test_logs_when_no_provider_configured(caplog):
    import logging
    with caplog.at_level(logging.INFO):
        send_email(make_settings(email_provider_url=''), 'user@example.test', 'Тема', 'Текст письма')
    assert 'user@example.test' in caplog.text
    assert 'Тема' in caplog.text


def test_posts_to_provider_when_configured(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return httpx.Response(200, request=httpx.Request('POST', url))

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(
        email_provider_url='https://email.example/send', email_provider_api_key='key123',
        email_sender_address='noreply@unicrm.tech', email_sender_name='UniCRM',
    )
    send_email(settings, 'user@example.test', 'Тема', 'Текст письма')
    assert len(calls) == 1
    url, body, headers = calls[0]
    assert url == 'https://email.example/send'
    assert body['to'] == 'user@example.test'
    assert body['subject'] == 'Тема'
    assert body['text'] == 'Текст письма'
    assert body['from'] == 'noreply@unicrm.tech'
    assert headers['Authorization'] == 'Bearer key123'


def test_raises_on_provider_failure(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError('boom')

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(email_provider_url='https://email.example/send')
    with pytest.raises(EmailSendError):
        send_email(settings, 'user@example.test', 'Тема', 'Текст письма')


def test_raises_on_non_2xx_response(monkeypatch):
    def fake_post(url, json, headers, timeout):
        return httpx.Response(500, request=httpx.Request('POST', url))

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(email_provider_url='https://email.example/send')
    with pytest.raises(EmailSendError):
        send_email(settings, 'user@example.test', 'Тема', 'Текст письма')


def test_from_address_overrides_the_settings_sender_address(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json)
        return httpx.Response(200, request=httpx.Request('POST', url))

    monkeypatch.setattr('httpx.post', fake_post)
    settings = make_settings(email_provider_url='https://email.example/send', email_sender_address='noreply@unicrm.tech')
    send_email(settings, 'user@example.test', 'Тема', 'Текст', from_address='info@unicrm.tech')
    assert calls[0]['from'] == 'info@unicrm.tech'
