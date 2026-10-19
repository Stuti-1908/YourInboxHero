"""GoHighLevel API Service — Internal escalation engine for SMS and Voice.

This service is NOT user-facing. It powers the automatic escalation
from Email → SMS → Voice calls when debtors ignore payment reminders.

Environment Variables Required:
    GHL_API_KEY      - Your GHL API Bearer token
    GHL_LOCATION_ID  - Your GHL Location/Sub-account ID
"""
import logging
import requests
from typing import Optional

from src.config.settings import get_settings

GHL_BASE_URL = "https://services.leadconnectorhq.com"


def _get_headers() -> dict:
    settings = get_settings()
    if not settings.ghl_api_key:
        logging.warning("GHL_API_KEY not set — SMS/Voice escalation disabled")
        return {}
    return {
        "Authorization": f"Bearer {settings.ghl_api_key}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }


def _get_location_id() -> str:
    return get_settings().ghl_location_id or ""


def _search_contact(headers: dict, location_id: str, query: str) -> Optional[str]:
    resp = requests.get(
        f"{GHL_BASE_URL}/contacts/",
        headers=headers,
        params={"locationId": location_id, "query": query}
    )
    resp.raise_for_status()
    contacts = resp.json().get("contacts", [])
    return contacts[0]["id"] if contacts else None


def find_or_create_contact(name: str, email: str, phone: str) -> Optional[str]:
    """Find an existing GHL contact by email, or create a new one.
    Returns the GHL contact ID or None if GHL is not configured."""
    headers = _get_headers()
    if not headers:
        return None
    location_id = _get_location_id()

    # Search by email first
    try:
        contact_id = _search_contact(headers, location_id, email)
        if contact_id:
            return contact_id
    except Exception as e:
        logging.error(f"GHL contact search failed: {e}")

    # Create new contact
    try:
        resp = requests.post(
            f"{GHL_BASE_URL}/contacts/",
            headers=headers,
            json={
                "locationId": location_id,
                "name": name,
                "email": email,
                "phone": phone
            }
        )
        resp.raise_for_status()
        return resp.json().get("contact", {}).get("id")
    except Exception as e:
        # GHL's search-by-query is a fuzzy text search, not an exact-match
        # lookup, so it can miss a contact that genuinely already exists
        # (indexing lag, formatting differences, etc.) -- when that happens,
        # creation fails with a 400 "duplicate contact" error. Re-searching
        # by phone (GHL's dedupe key for this error) recovers the existing
        # contact instead of permanently failing SMS/voice for any debtor
        # who already has a GHL contact from a prior reminder.
        logging.error(f"GHL contact creation failed: {e}")
        try:
            contact_id = _search_contact(headers, location_id, phone)
            if contact_id:
                return contact_id
        except Exception as e2:
            logging.error(f"GHL contact re-search after failed creation also failed: {e2}")
        return None


# GHL custom field keys the Voice AI agent prompts reference via
# {{contact.<key>}} -- created once via POST /locations/{id}/customFields
# (see the YourInboxHero GHL location's custom field list). Writing these
# before tagging a contact for voice_escalation is what lets a single
# shared agent per product (invoice vs document) read per-call details
# instead of speaking a generic, unpersonalized message.
_VOICE_CALL_FIELD_KEYS = {
    "contact_name": "voice_call_contact_name",
    "company_name": "voice_call_company_name",
    "reason": "voice_call_reason",
    "item_description": "voice_call_item_description",
    "amount": "voice_call_amount",
    "due_date": "voice_call_due_date",
}


def _set_contact_voice_call_fields(contact_id: str, headers: dict, **fields) -> bool:
    """Write the per-call personalization fields onto a GHL contact so the
    Voice AI agent's prompt can read them via {{contact.<field_key>}}.
    Unknown kwargs are ignored; missing ones are sent as empty strings so a
    stale value from a prior call never leaks into this one."""
    custom_fields = [
        {"key": key, "field_value": str(fields.get(short_key, "") or "")}
        for short_key, key in _VOICE_CALL_FIELD_KEYS.items()
    ]
    try:
        resp = requests.put(
            f"{GHL_BASE_URL}/contacts/{contact_id}",
            headers=headers,
            json={"customFields": custom_fields},
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"GHL contact custom field update failed: {e}")
        return False


def send_sms(phone: str, message: str, contact_name: str = "", contact_email: str = "") -> bool:
    """Send an SMS message via GHL Conversations API.
    Returns True if successful, False otherwise."""
    headers = _get_headers()
    if not headers:
        logging.info("GHL not configured — skipping SMS")
        return False

    # Ensure we have a contact in GHL
    contact_id = find_or_create_contact(contact_name, contact_email, phone)
    if not contact_id:
        logging.error(f"Could not find/create GHL contact for {phone}")
        return False

    try:
        resp = requests.post(
            f"{GHL_BASE_URL}/conversations/messages",
            headers=headers,
            json={
                "type": "SMS",
                "contactId": contact_id,
                "message": message
            }
        )
        resp.raise_for_status()
        logging.info(f"SMS sent to {phone} via GHL")
        return True
    except Exception as e:
        logging.error(f"GHL SMS send failed: {e}")
        return False


def trigger_voice_call(
    phone: str,
    message: str,
    contact_name: str = "",
    contact_email: str = "",
    company_name: str = "",
    reason: str = "",
    item_description: str = "",
    amount: str = "",
    due_date: str = "",
) -> bool:
    """Trigger an automated voice call via GHL Workflow.

    This uses GHL's workflow trigger to initiate a call. The tag applied
    is 'voice_escalation_<reason>' (e.g. 'voice_escalation_invoice',
    'voice_escalation_document') rather than one shared tag, so GHL can
    route each reason to its own Workflow + Voice AI agent without a
    conditional filter step -- invoice and document calls need different
    scripts (payment ask vs. document reminder) and were originally going
    to share one workflow/agent with no way to distinguish them.
    You must set up a Workflow in GHL per reason:
      1. Has a 'Contact Tag Added' trigger for tag 'voice_escalation_<reason>'
      2. Contains a Voice AI Outbound Call action (using the agent built
         for that reason) whose prompt references {{contact.voice_call_*}}
         for personalization

    Writes the personalization fields (see _VOICE_CALL_FIELD_KEYS) onto
    the GHL contact BEFORE tagging, so by the time the tag-add trigger
    fires, the agent reads this call's details rather than a stale value
    from a previous escalation (or none at all).

    `message` is currently unused by GHL's Voice AI action (which reads
    the contact fields + the agent's own fixed prompt, not a per-call
    string) -- kept as a parameter for backwards compatibility with
    callers and in case a future GHL action type accepts free text.

    Returns True if the workflow was triggered, False otherwise.
    """
    headers = _get_headers()
    if not headers:
        logging.info("GHL not configured — skipping voice call")
        return False

    contact_id = find_or_create_contact(contact_name, contact_email, phone)
    if not contact_id:
        logging.error(f"Could not find/create GHL contact for {phone}")
        return False

    _set_contact_voice_call_fields(
        contact_id,
        headers,
        contact_name=contact_name,
        company_name=company_name,
        reason=reason,
        item_description=item_description,
        amount=amount,
        due_date=due_date,
    )

    tag = f"voice_escalation_{reason}" if reason else "voice_escalation"
    try:
        # Add a reason-specific tag so GHL can route invoice vs document
        # calls to their own Workflow + Voice AI agent.
        resp = requests.post(
            f"{GHL_BASE_URL}/contacts/{contact_id}/tags",
            headers=headers,
            json={"tags": [tag]}
        )
        resp.raise_for_status()
        logging.info(f"Voice call workflow triggered for {phone} via GHL (tag={tag})")
        return True
    except Exception as e:
        logging.error(f"GHL voice trigger failed: {e}")
        return False
