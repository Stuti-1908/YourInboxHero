import pytest
from unittest.mock import patch, MagicMock
from src.services.email import send_reminder_email, render_template
from src.services.secrets import encrypt_secret
from src.models.invoice import InvoiceStatus
from datetime import date


def _make_dummy_invoice(plan='scale', smtp_configured=False):
    class DummyUser:
        id = "test-id"
        company_name = 'Test Company'
        username = 'test@example.com'
        subscription_plan = plan
        logo_base64 = None
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
        description = None
        due_date = date(2023, 1, 15)
        payment_instructions = 'Pay via wire transfer.'
        status = InvoiceStatus.upcoming
        payment_link = None
        debtor = DummyDebtor(user_id='test-id')

    return DummyInvoice()


def test_send_email_calls_resend(monkeypatch):
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.EmailTemplate'), \
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

    with patch('src.services.email.EmailTemplate'), \
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
    with patch('src.services.email.EmailTemplate'), \
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


def test_reminder_email_attaches_generated_pdf(monkeypatch):
    """The default (non-custom-template) reminder email should include a
    PDF copy of the invoice as a real attachment, base64-encoded for
    Resend's API -- not just mention the invoice in the email body."""
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.EmailTemplate'), \
        patch('src.services.email.SessionLocal') as mock_session_local, \
        patch('src.services.email.requests.post') as mock_post:
        mock_session_local.return_value.query.return_value.filter.return_value.first.return_value = None
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        send_reminder_email(_make_dummy_invoice())

        call_kwargs = mock_post.call_args.kwargs
        attachments = call_kwargs['json'].get('attachments')
        assert attachments is not None and len(attachments) == 1
        assert attachments[0]['filename'] == 'invoice_INV-123.pdf'
        # Real PDF bytes, base64-encoded (not raw bytes, which Resend's
        # JSON API can't carry) -- decoding it should start with the PDF
        # magic header.
        import base64
        decoded = base64.b64decode(attachments[0]['content'])
        assert decoded[:4] == b'%PDF'


def test_reminder_email_sends_even_if_pdf_generation_fails(monkeypatch):
    """A PDF generation failure (malformed data, unexpected exception,
    etc.) must not block the reminder email itself -- the email's own
    invoice details still cover the essentials without the attachment."""
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.EmailTemplate'), \
        patch('src.services.email.SessionLocal') as mock_session_local, \
        patch('src.services.pdf_service.generate_invoice_pdf', side_effect=RuntimeError("boom")), \
        patch('src.services.email.requests.post') as mock_post:
        mock_session_local.return_value.query.return_value.filter.return_value.first.return_value = None
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        response = send_reminder_email(_make_dummy_invoice())

        assert response["status"] == "success"
        call_kwargs = mock_post.call_args.kwargs
        assert 'attachments' not in call_kwargs['json']


def test_render_template_wording_varies_by_status():
    """The three automated-reminder statuses (upcoming/due/overdue) must
    produce visibly different banner text, so a debtor can't mistake an
    overdue notice for a routine heads-up."""
    invoice = _make_dummy_invoice()

    invoice.status = InvoiceStatus.upcoming
    upcoming_html = render_template(invoice)
    assert 'Upcoming Invoice' in upcoming_html

    invoice.status = InvoiceStatus.due
    due_html = render_template(invoice)
    assert 'Invoice Due Today' in due_html

    invoice.status = InvoiceStatus.overdue
    overdue_html = render_template(invoice)
    assert 'Payment Overdue' in overdue_html
    assert 'past its due date' in overdue_html


def test_render_template_includes_payment_link_button():
    invoice = _make_dummy_invoice()
    invoice.payment_link = 'https://pay.example.com/abc123'

    html = render_template(invoice)

    assert 'https://pay.example.com/abc123' in html
    assert 'Pay $1000.50 Now' in html


def test_render_template_omits_payment_button_when_no_link():
    invoice = _make_dummy_invoice()
    invoice.payment_link = None

    html = render_template(invoice)

    assert 'Pay $1000.50 Now' not in html
