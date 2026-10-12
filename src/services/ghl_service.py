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


def trigger_voice_call(phone: str, message: str, contact_name: str = "", contact_email: str = "") -> bool:
    """Trigger an automated voice call via GHL Workflow.
    
    This uses GHL's workflow trigger to initiate a call.
    You must set up a Workflow in GHL that:
      1. Has a 'Contact Tag Added' trigger for tag 'voice_escalation'
      2. Contains a 'Call' action with text-to-speech
    
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

    try:
        # Add a tag to trigger the voice workflow
        resp = requests.post(
            f"{GHL_BASE_URL}/contacts/{contact_id}/tags",
            headers=headers,
            json={"tags": ["voice_escalation"]}
        )
        resp.raise_for_status()
        logging.info(f"Voice call workflow triggered for {phone} via GHL")
        return True
    except Exception as e:
        logging.error(f"GHL voice trigger failed: {e}")
        return False
