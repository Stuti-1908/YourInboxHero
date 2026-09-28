import pytest
from unittest.mock import patch, MagicMock
from src.services.email import send_reminder_email
from datetime import date


def _make_dummy_invoice():
    class DummyUser:
        id = "test-id"
        company_name = 'Test Company'
        smtp_host = None
        smtp_port = None
        smtp_username = None
        smtp_password = None
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
