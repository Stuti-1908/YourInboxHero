"""Tests for document_email.py — mirrors test_email.py for invoice
reminders."""
import pytest
from unittest.mock import patch, MagicMock
from src.services.document_email import send_document_request_email, render_document_request_email
from src.services.secrets import encrypt_secret


def _make_dummy_doc_request(plan='scale', smtp_configured=False, status='pending'):
    class DummyUser:
        id = "test-id"
        company_name = 'Test Company'
        username = 'test@example.com'
        subscription_plan = plan
        smtp_host = 'smtp.example.com' if smtp_configured else None
        smtp_port = '587' if smtp_configured else None
        smtp_username = 'user@example.com' if smtp_configured else None
        smtp_password = encrypt_secret('hunter2') if smtp_configured else None
        smtp_from_email = None

    class DummyClient:
        email = 'client@example.com'
        name = 'Acme Corp'
        user = DummyUser()

    class DummyDocRequest:
        id = "test-doc-request-id"
        title = "W-9 Tax Form"
        description = "Please provide your latest W-9"
        due_date = "2026-10-20"
        upload_token = "doc_abc123"
        client = DummyClient()
        user = DummyClient.user  # DocumentRequest.user is the business owner, same User as client.user

    DummyDocRequest.status = status
    return DummyDocRequest()


def test_send_document_request_email_calls_resend(monkeypatch):
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        response = send_document_request_email(_make_dummy_doc_request())

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs['json']['to'] == ['client@example.com']
        assert response["status"] == "success"
        assert response["method"] == "resend"


def test_send_document_request_email_raises_when_resend_fails(monkeypatch):
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.email.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response

        with pytest.raises(Exception):
            send_document_request_email(_make_dummy_doc_request())


def test_starter_plan_ignores_saved_smtp_and_uses_resend(monkeypatch):
    monkeypatch.setattr('src.services.email.settings.resend_api_key', 'test-key')

    with patch('src.services.document_email._send_via_smtp') as mock_smtp, \
        patch('src.services.email.requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "resend-msg-id"}
        mock_post.return_value = mock_response

        result = send_document_request_email(_make_dummy_doc_request(plan='starter', smtp_configured=True))

        mock_smtp.assert_not_called()
        mock_post.assert_called_once()
        assert result["method"] == "resend"


def test_growth_plan_uses_saved_smtp_when_configured(monkeypatch):
    with patch('src.services.document_email._send_via_smtp') as mock_smtp, \
         patch('src.services.email.requests.post') as mock_post:
        mock_smtp.return_value = {"status": "success", "method": "smtp"}

        result = send_document_request_email(_make_dummy_doc_request(plan='growth', smtp_configured=True))

        mock_smtp.assert_called_once()
        mock_post.assert_not_called()
        assert result["method"] == "smtp"
        assert mock_smtp.call_args.kwargs['password'] == 'hunter2'


def test_render_wording_varies_by_status():
    """pending vs. overdue must produce visibly different banner text."""
    doc = _make_dummy_doc_request(status='pending')
    pending_html = render_document_request_email(doc)
    assert 'Document Requested' in pending_html

    doc.status = 'overdue'
    overdue_html = render_document_request_email(doc)
    assert 'Document Overdue' in overdue_html
    assert 'past its due date' in overdue_html


def test_render_includes_upload_link_and_branding():
    doc = _make_dummy_doc_request()
    html = render_document_request_email(doc)

    assert 'Test Company' in html
    assert 'doc_abc123' in html
    assert 'Upload Document' in html
    assert 'W-9 Tax Form' in html
