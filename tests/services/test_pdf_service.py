"""Tests for the Growth+ plan gate on invoice PDF logo branding."""
import base64
from unittest.mock import patch
from src.services.pdf_service import generate_invoice_pdf

# A valid 1x1 transparent PNG, base64-encoded, as a stand-in for a real
# uploaded logo.
TINY_PNG_B64 = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "0000"
    "0049454e44ae426082"
)).decode()


class DummyDebtor:
    name = "Acme Corp"
    email = "ap@acme.com"


class DummyInvoice:
    invoice_number = "INV-001"
    due_date = "2026-10-01"
    status = "upcoming"
    description = "Consulting"
    amount = "1000.00"
    payment_instructions = None


def _make_user(plan, logo=None):
    class DummyUser:
        username = "user@example.com"
        company_name = "My Company"
        subscription_plan = plan
        logo_base64 = logo
    return DummyUser()


def test_logo_applied_on_growth_plan():
    user = _make_user("growth", logo=f"data:image/png;base64,{TINY_PNG_B64}")
    with patch('src.services.pdf_service.Image') as mock_image:
        generate_invoice_pdf(DummyInvoice(), DummyDebtor(), user)
        mock_image.assert_called_once()


def test_logo_not_applied_on_starter_plan_even_if_saved():
    """A Starter user may have a logo saved (saving isn't blocked) but it
    must not render until they're on a plan that includes branding."""
    user = _make_user("starter", logo=f"data:image/png;base64,{TINY_PNG_B64}")
    with patch('src.services.pdf_service.Image') as mock_image:
        generate_invoice_pdf(DummyInvoice(), DummyDebtor(), user)
        mock_image.assert_not_called()


def test_no_logo_saved_at_all_on_growth_plan():
    user = _make_user("growth", logo=None)
    with patch('src.services.pdf_service.Image') as mock_image:
        generate_invoice_pdf(DummyInvoice(), DummyDebtor(), user)
        mock_image.assert_not_called()
