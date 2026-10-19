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


def test_find_or_create_contact_recovers_from_duplicate_on_create(monkeypatch):
    """Regression test: GHL's search is a fuzzy text search, not an exact
    match, so it can miss a contact that actually exists (indexing lag,
    formatting, etc.). When that happens, POST /contacts/ fails with a 400
    duplicate-contact error. We must re-search (by phone) and recover the
    existing contact rather than permanently failing SMS/voice for that
    debtor on every future chase."""
    _mock_settings(monkeypatch)

    empty_search_resp = MagicMock()
    empty_search_resp.json.return_value = {"contacts": []}
    empty_search_resp.raise_for_status = lambda: None

    create_resp = MagicMock()
    create_resp.raise_for_status = MagicMock(side_effect=Exception("400 Client Error: Bad Request"))

    found_by_phone_resp = MagicMock()
    found_by_phone_resp.json.return_value = {"contacts": [{"id": "existing-contact-1"}]}
    found_by_phone_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", side_effect=[empty_search_resp, found_by_phone_resp]) as mock_get, \
        patch("src.services.ghl_service.requests.post", return_value=create_resp):
        contact_id = ghl_service.find_or_create_contact("Jane Doe", "jane@example.com", "+15551234567")

    assert contact_id == "existing-contact-1"
    assert mock_get.call_count == 2
    second_call_params = mock_get.call_args_list[1].kwargs["params"]
    assert second_call_params["query"] == "+15551234567"


def test_find_or_create_contact_returns_none_when_create_and_research_both_fail(monkeypatch):
    _mock_settings(monkeypatch)

    empty_search_resp = MagicMock()
    empty_search_resp.json.return_value = {"contacts": []}
    empty_search_resp.raise_for_status = lambda: None

    create_resp = MagicMock()
    create_resp.raise_for_status = MagicMock(side_effect=Exception("400 Client Error: Bad Request"))

    with patch("src.services.ghl_service.requests.get", side_effect=[empty_search_resp, Exception("network error")]), \
        patch("src.services.ghl_service.requests.post", return_value=create_resp):
        contact_id = ghl_service.find_or_create_contact("Jane Doe", "jane@example.com", "+15551234567")

    assert contact_id is None


def test_send_sms_fails_when_contact_lookup_fails(monkeypatch):
    _mock_settings(monkeypatch)
    with patch("src.services.ghl_service.requests.get", side_effect=Exception("network error")), \
        patch("src.services.ghl_service.requests.post", side_effect=Exception("network error")):
        result = ghl_service.send_sms(phone="+15551234567", message="hi")

    assert result is False


def test_trigger_voice_call_tags_contact(monkeypatch):
    """Confirms the current implementation: this tags the contact for a GHL
    Voice AI Workflow to pick up and does not pass the message text
    anywhere (GHL's Voice AI action reads contact custom fields + its own
    fixed agent prompt, not a per-call string)."""
    _mock_settings(monkeypatch)
    contact_resp = MagicMock()
    contact_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    contact_resp.raise_for_status = lambda: None

    tag_resp = MagicMock()
    tag_resp.raise_for_status = lambda: None

    put_resp = MagicMock()
    put_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=contact_resp), \
        patch("src.services.ghl_service.requests.put", return_value=put_resp), \
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
    # No reason passed -> falls back to the original shared tag name.
    assert call_kwargs["json"]["tags"] == ["voice_escalation"]
    # The message text is accepted by the function signature but never sent
    # to GHL anywhere in the request — flagging via assertion so this test
    # breaks (intentionally) if/when that gap gets fixed, as a reminder to
    # update this test alongside it.
    assert "message" not in call_kwargs["json"]


def test_trigger_voice_call_tags_contact_with_reason_specific_tag(monkeypatch):
    """Passing reason="invoice"/"document" must produce a distinct tag per
    reason, so GHL can route each to its own Workflow + Voice AI agent
    without a conditional filter step."""
    _mock_settings(monkeypatch)
    contact_resp = MagicMock()
    contact_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    contact_resp.raise_for_status = lambda: None

    tag_resp = MagicMock()
    tag_resp.raise_for_status = lambda: None

    put_resp = MagicMock()
    put_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=contact_resp), \
        patch("src.services.ghl_service.requests.put", return_value=put_resp), \
        patch("src.services.ghl_service.requests.post", return_value=tag_resp) as mock_post:
        result = ghl_service.trigger_voice_call(
            phone="+15551234567",
            message="unused",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
            reason="document",
        )

    assert result is True
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["tags"] == ["voice_escalation_document"]


def test_trigger_voice_call_writes_personalization_fields_before_tagging(monkeypatch):
    """The contact's GHL custom fields (read by the Voice AI agent's prompt
    via {{contact.voice_call_*}}) must be written before the tag that
    triggers the call, so the agent never reads a stale value from a prior
    escalation."""
    _mock_settings(monkeypatch)
    contact_resp = MagicMock()
    contact_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    contact_resp.raise_for_status = lambda: None

    tag_resp = MagicMock()
    tag_resp.raise_for_status = lambda: None

    put_resp = MagicMock()
    put_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=contact_resp), \
        patch("src.services.ghl_service.requests.put", return_value=put_resp) as mock_put, \
        patch("src.services.ghl_service.requests.post", return_value=tag_resp):
        result = ghl_service.trigger_voice_call(
            phone="+15551234567",
            message="unused",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
            company_name="Acme Inc",
            reason="invoice",
            item_description="INV-1001",
            amount="500.00",
            due_date="2026-10-01",
        )

    assert result is True
    mock_put.assert_called_once()
    body = mock_put.call_args.kwargs["json"]
    fields_by_key = {f["key"]: f["field_value"] for f in body["customFields"]}
    assert fields_by_key["voice_call_contact_name"] == "Jane Doe"
    assert fields_by_key["voice_call_company_name"] == "Acme Inc"
    assert fields_by_key["voice_call_reason"] == "invoice"
    assert fields_by_key["voice_call_item_description"] == "INV-1001"
    assert fields_by_key["voice_call_amount"] == "500.00"
    assert fields_by_key["voice_call_due_date"] == "2026-10-01"


def test_trigger_voice_call_still_tags_even_if_custom_field_write_fails(monkeypatch):
    """A generic (unpersonalized) call is better than no call at all -- a
    failed custom-field write must not block the tag-add that actually
    triggers the call."""
    _mock_settings(monkeypatch)
    contact_resp = MagicMock()
    contact_resp.json.return_value = {"contacts": [{"id": "contact-1"}]}
    contact_resp.raise_for_status = lambda: None

    tag_resp = MagicMock()
    tag_resp.raise_for_status = lambda: None

    with patch("src.services.ghl_service.requests.get", return_value=contact_resp), \
        patch("src.services.ghl_service.requests.put", side_effect=Exception("network error")), \
        patch("src.services.ghl_service.requests.post", return_value=tag_resp) as mock_post:
        result = ghl_service.trigger_voice_call(
            phone="+15551234567",
            message="unused",
            contact_name="Jane Doe",
            contact_email="jane@example.com",
        )

    assert result is True
    mock_post.assert_called_once()
