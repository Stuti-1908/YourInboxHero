"""Tests for invoice PDF generation: the Growth+ plan gate on logo
branding, and the redesigned layout's actual rendered content."""
import base64
from datetime import date, datetime, timezone
from unittest.mock import patch
from pypdf import PdfReader
from src.services.pdf_service import generate_invoice_pdf
from src.models.invoice import InvoiceStatus

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
    phone = None


class DummyInvoice:
    invoice_number = "INV-001"
    created_at = None
    due_date = "2026-10-01"
    status = "upcoming"
    description = "Consulting"
    amount = "1000.00"
    payment_link = None
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


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(__import__('io').BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def _full_invoice(status=InvoiceStatus.upcoming):
    class FullInvoice:
        invoice_number = "INV-2026-0142"
        created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
        due_date = date(2026, 10, 20)
    FullInvoice.status = status
    FullInvoice.description = "Q4 Strategic Consulting Retainer"
    FullInvoice.amount = 4875.00
    FullInvoice.payment_link = "https://buy.stripe.com/test_demo123"
    FullInvoice.payment_instructions = "Wire transfer to Acme Bank, Account 0123456789"
    return FullInvoice()


def _full_debtor():
    class FullDebtor:
        name = "Jordan Smith"
        email = "ap@acmeindustries.com"
        phone = "+15552345678"
    return FullDebtor()


def test_pdf_contains_real_invoice_structure_not_just_a_field_list():
    """Confirms the redesigned layout actually renders: a big INVOICE
    header, From/Bill To, invoice number/dates, itemized description,
    and a Subtotal distinct from Total Due -- not just that the function
    doesn't crash."""
    user = _make_user("growth", logo=None)
    buf = generate_invoice_pdf(_full_invoice(), _full_debtor(), user)
    text = _extract_text(buf.getvalue())

    assert "INVOICE" in text
    assert "FROM" in text
    assert "BILL TO" in text
    assert "Jordan Smith" in text
    assert "ap@acmeindustries.com" in text
    assert "INV-2026-0142" in text
    assert "2026-10-01" in text  # issue date
    assert "2026-10-20" in text  # due date
    assert "Q4 Strategic Consulting Retainer" in text
    assert "$4,875.00" in text  # comma-formatted currency, not raw "4875.0"
    assert "Subtotal" in text
    assert "Total Due" in text


def test_pdf_status_badge_shows_actual_status():
    user = _make_user("growth", logo=None)

    overdue_text = _extract_text(generate_invoice_pdf(_full_invoice(InvoiceStatus.overdue), _full_debtor(), user).getvalue())
    assert "OVERDUE" in overdue_text

    paid_text = _extract_text(generate_invoice_pdf(_full_invoice(InvoiceStatus.paid), _full_debtor(), user).getvalue())
    assert "PAID" in paid_text


def test_pdf_includes_payment_link_and_instructions_when_present():
    user = _make_user("growth", logo=None)
    text = _extract_text(generate_invoice_pdf(_full_invoice(), _full_debtor(), user).getvalue())

    assert "https://buy.stripe.com/test_demo123" in text
    assert "Wire transfer to Acme Bank" in text


def test_pdf_omits_optional_sections_cleanly_when_absent():
    """A minimal invoice (no description, no payment link, no
    instructions, no debtor phone) must still render a valid, sensible
    PDF rather than blank sections or a crash."""
    user = _make_user("growth", logo=None)
    invoice = DummyInvoice()
    invoice.description = None
    invoice.payment_link = None
    invoice.payment_instructions = None
    invoice.created_at = None

    text = _extract_text(generate_invoice_pdf(invoice, DummyDebtor(), user).getvalue())

    assert "Services rendered" in text  # fallback description
    assert "PAYMENT LINK" not in text
    assert "PAYMENT INSTRUCTIONS" not in text
