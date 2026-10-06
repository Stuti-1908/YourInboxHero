import pytest
from unittest.mock import patch, MagicMock
from src.services.email import send_reminder_email
from src.services.secrets import encrypt_secret
from datetime import date


def _make_dummy_invoice(plan='scale', smtp_configured=False):
    class DummyUser:
        id = "test-id"
        company_name = 'Test Company'
        subscription_plan = plan
        smtp_host = 'smtp.example.com' if smtp_configured else None
        smtp_port = '587' if smtp_configured else None
        smtp_username = 'user@example.com' if smtp_configured else None
        # Stored at rest encrypted — email.py decrypts it before use, so
        # the fixture must mirror what's actually in the DB, not a
        # plaintext value a real row would never contain.
        smtp_password = encrypt_secret('hunter2') if smtp_configured else None
        smtp_from_email = None

    class DummyDebtor:
        email = 'client@example.com'
        name = 'Acme Corp'
        user = DummyUser()
        def __init__(self, user_id=None):
            self.user_id = user_id

    class DummyInvoice:
        id = "test-invoice-id"
        invoice_number = 'INV-123'
        amount = 1000.50
        due_date = date(2023, 1, 15)
        payment_instructions = 'Pay via wire transfer.'
        status = type('Status', (), {'value': 'upcoming'})()
        payment_link = None
        debtor = DummyDebtor(user_id='test-id')

    return DummyInvoice()


def test_send_email_calls_resend(monkeypatch):
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.EmailTemplate') as mock_template, \
         patch('src.services.email.SessionLocal') as mock_session_local, \
         patch('src.services.email.requests.post') as mock_post:
        mock_session_local.return_value.query.return_value.filter.return_value.first.return_value = None
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        response = send_reminder_email(_make_dummy_invoice())

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs['json']['to'] == ['client@example.com']
        assert response["status"] == "success"
        assert response["method"] == "resend"
        assert response["status_code"] == 200


def test_send_email_raises_when_resend_fails(monkeypatch):
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.SessionLocal') as mock_session_local, \
         patch('src.services.email.requests.post') as mock_post:
        mock_session_local.return_value.query.return_value.filter.return_value.first.return_value = None
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response

        with pytest.raises(Exception):
            send_reminder_email(_make_dummy_invoice())


def test_starter_plan_ignores_saved_smtp_and_uses_resend(monkeypatch):
    """A Starter user may have SMTP credentials saved (saving isn't
    blocked), but custom_smtp is Growth+ -- sending must still go through
    Resend, never attempt the user's own SMTP server."""
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.EmailTemplate') as mock_template, \
         patch('src.services.email.SessionLocal') as mock_session_local, \
         patch('src.services.email._send_via_smtp') as mock_smtp, \
         patch('src.services.email.requests.post') as mock_post:
        mock_session_local.return_value.query.return_value.filter.return_value.first.return_value = None
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        result = send_reminder_email(_make_dummy_invoice(plan='starter', smtp_configured=True))

        mock_smtp.assert_not_called()
        mock_post.assert_called_once()
        assert result["method"] == "resend"


def test_growth_plan_uses_saved_smtp_when_configured(monkeypatch):
    with patch('src.services.email.EmailTemplate') as mock_template, \
         patch('src.services.email.SessionLocal') as mock_session_local, \
         patch('src.services.email._send_via_smtp') as mock_smtp, \
         patch('src.services.email.requests.post') as mock_post:
        mock_session_local.return_value.query.return_value.filter.return_value.first.return_value = None
        mock_smtp.return_value = {"status": "success", "method": "smtp"}

        result = send_reminder_email(_make_dummy_invoice(plan='growth', smtp_configured=True))

        mock_smtp.assert_called_once()
        mock_post.assert_not_called()
        assert result["method"] == "smtp"
        # The stored value is encrypted; _send_via_smtp must receive the
        # decrypted plaintext, not the ciphertext itself.
        assert mock_smtp.call_args.kwargs['password'] == 'hunter2'


def test_starter_plan_ignores_saved_custom_template(monkeypatch):
    """custom_templates is Growth+ -- a Starter user's saved template (if
    any somehow exists, e.g. after a downgrade) must not be looked up or
    used; the default built-in template always applies instead."""
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.SessionLocal') as mock_session_local, \
         patch('src.services.email.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        send_reminder_email(_make_dummy_invoice(plan='starter'))

        # The DB should never even be queried for a template on Starter.
        mock_session_local.assert_not_called()
