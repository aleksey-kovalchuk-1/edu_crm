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


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.tls = self.logged_in = False
        self.messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        if getattr(self, 'fail', False):
            import smtplib
            raise smtplib.SMTPException('rejected')
        self.messages.append(message)


def _smtp_settings(**overrides):
    values = {'email_smtp_host': 'smtp.yandex.ru', 'email_smtp_port': 465, 'email_smtp_user': 'noreply@school.ru',
              'email_smtp_password': 'secret', 'email_sender_address': 'noreply@school.ru', 'email_sender_name': 'UniCRM'}
    return make_settings(**{**values, **overrides})


def test_sends_over_ssl_smtp_to_the_russian_mailbox(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr('smtplib.SMTP_SSL', lambda host, port, timeout, context=None: FakeSMTP(host, port, timeout))
    send_email(_smtp_settings(), 'ivanov@mail.ru', 'Тема', 'Текст письма')
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port, smtp.logged_in) == ('smtp.yandex.ru', 465, ('noreply@school.ru', 'secret'))
    message = smtp.messages[0]
    assert message['To'] == 'ivanov@mail.ru'
    assert message['Subject'] == 'Тема'
    assert 'noreply@school.ru' in message['From'] and 'UniCRM' in message['From']
    assert message.get_content().strip() == 'Текст письма'


def test_port_587_uses_starttls(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr('smtplib.SMTP', FakeSMTP)
    send_email(_smtp_settings(email_smtp_port=587), 'ivanov@mail.ru', 'Тема', 'Текст')
    assert FakeSMTP.instances[0].tls is True


def test_an_smtp_failure_raises_email_send_error(monkeypatch):
    def failing(host, port, timeout, context=None):
        smtp = FakeSMTP(host, port, timeout)
        smtp.fail = True
        return smtp
    monkeypatch.setattr('smtplib.SMTP_SSL', failing)
    with pytest.raises(EmailSendError):
        send_email(_smtp_settings(), 'ivanov@mail.ru', 'Тема', 'Текст')


def test_only_a_real_provider_counts_as_configured():
    from app.email import email_configured
    assert email_configured(_smtp_settings()) is True
    assert email_configured(make_settings(email_provider_url='https://email.example/send')) is True
    assert email_configured(make_settings()) is False
