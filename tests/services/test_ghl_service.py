"""Tests for the GoHighLevel service — contact lookup/creation, SMS sending,
and voice-call triggering, plus the "GHL not configured" fallback paths."""
from unittest.mock import patch, MagicMock

from src.services import ghl_service


def _mock_settings(monkeypatch, api_key="test-key", location_id="loc-123"):
    settings = MagicMock()
    settings.ghl_api_key = api_key
    settings.ghl_location_id = location_id
    monkeypatch.setattr(ghl_service, "get_settings", lambda: settings)


def test_headers_empty_when_no_api_key(monkeypatch):
    _mock_settings(monkeypatch, api_key=None)
    assert ghl_service._get_headers() == {}


def test_headers_include_bearer_token_when_configured(monkeypatch):
    _mock_settings(monkeypatch, api_key="abc123")
    headers = ghl_service._get_headers()
    assert headers["Authorization"] == "Bearer abc123"


def test_location_id_falls_back_to_empty_string(monkeypatch):
    _mock_settings(monkeypatch, location_id=None)
    assert ghl_service._get_location_id() == ""


def test_send_sms_skips_when_not_configured(monkeypatch):
    _mock_settings(monkeypatch, api_key=None)
    result = ghl_service.send_sms(phone="+15551234567", message="hi")
    assert result is False


def test_trigger_voice_call_skips_when_not_configured(monkeypatch):
    _mock_settings(monkeypatch, api_key=None)
    result = ghl_service.trigger_voice_call(phone="+15551234567", message="hi")
    assert result is False


def test_find_or_create_contact_returns_existing(monkeypatch):
    _mock_settings(monkeypatch)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    mock_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=mock_resp) as mock_get:
        contact_id = ghl_service.find_or_create_contact("Jane Doe", "jane@example.com", "+15551234567")

    assert contact_id == "contact-1"
    mock_get.assert_called_once()


def test_find_or_create_contact_creates_when_not_found(monkeypatch):
    _mock_settings(monkeypatch)
    search_resp = MagicMock()
    search_resp.json.return_value = {"contacts": []}
    search_resp.raise_for_status = lambda: None

    create_resp = MagicMock()
    create_resp.json.return_value = {"contact": {"id": "new-contact-1"}}
    create_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=search_resp), \
        patch("src.services.ghl_service.requests.post", return_value=create_resp) as mock_post:
        contact_id = ghl_service.find_or_create_contact("Jane Doe", "jane@example.com", "+15551234567")

    assert contact_id == "new-contact-1"
    mock_post.assert_called_once()


def test_send_sms_success(monkeypatch):
    _mock_settings(monkeypatch)
    contact_resp = MagicMock()
    contact_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    contact_resp.raise_for_status = lambda: None

    sms_resp = MagicMock()
    sms_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=contact_resp), \
        patch("src.services.ghl_service.requests.post", return_value=sms_resp) as mock_post:
        result = ghl_service.send_sms(
            phone="+15551234567",
            message="Your invoice is overdue",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
        )

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["type"] == "SMS"
    assert call_kwargs["json"]["contactId"] == "contact-1"


def test_send_sms_fails_when_contact_lookup_fails(monkeypatch):
    _mock_settings(monkeypatch)
    with patch("src.services.ghl_service.requests.get", side_effect=Exception("network error")), \
        patch("src.services.ghl_service.requests.post", side_effect=Exception("network error")):
        result = ghl_service.send_sms(phone="+15551234567", message="hi")

    assert result is False


def test_trigger_voice_call_tags_contact(monkeypatch):
    """Confirms the current implementation: this only tags the contact for a
    GHL Workflow to pick up (human warm-transfer), it does not place an
    automated call itself and does not pass the message text anywhere."""
    _mock_settings(monkeypatch)
    contact_resp = MagicMock()
    contact_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    contact_resp.raise_for_status = lambda: None

    tag_resp = MagicMock()
    tag_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=contact_resp), \
        patch("src.services.ghl_service.requests.post", return_value=tag_resp) as mock_post:
        result = ghl_service.trigger_voice_call(
            phone="+15551234567",
            message="Your invoice is overdue, please call us back",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
        )

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["tags"] == ["voice_escalation"]
    # The message text is accepted by the function signature but never sent
    # to GHL anywhere in the request — flagging via assertion so this test
    # breaks (intentionally) if/when that gap gets fixed, as a reminder to
    # update this test alongside it.
    assert "message" not in call_kwargs["json"]
