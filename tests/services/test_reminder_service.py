"""Tests for reminder_service — get_eligible_invoices and process_due_reminders.

Fixtures create 3 invoices with distinct due-date scenarios to verify
that only the correct invoice is returned by the eligibility query.
"""
import os
import uuid
import tempfile
from datetime import date, timedelta

# Point at a fresh SQLite file for test isolation
_db_file = tempfile.mktemp(suffix=".db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["SENDGRID_API_KEY"] = "SG.test"

from unittest.mock import patch, MagicMock

from src.db import engine, SessionLocal
from src.models.base import Base
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models import reminder  # noqa: F401 — register ReminderLog table

# Create all tables in the test database
Base.metadata.create_all(bind=engine)


def _make_debtor(session, name="Acme Corp", email=None):
    d = Debtor(
        id=str(uuid.uuid4()),
        name=name,
        email=email or f"{uuid.uuid4().hex[:8]}@example.com",
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def _make_invoice(session, debtor, due_date, status=InvoiceStatus.upcoming):
    inv = Invoice(
        id=str(uuid.uuid4()),
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=1000.00,
        due_date=due_date,
        status=status,
    )
    session.add(inv)
    session.flush()
    return inv


# ── Tests ────────────────────────────────────────────────────────────────────

def test_get_eligible_returns_only_upcoming_within_window():
    """Create 3 invoices:
      1. due tomorrow  (upcoming) → ELIGIBLE
      2. due yesterday (overdue status) → NOT eligible (past due)
      3. due in 30 days (upcoming) → NOT eligible (outside 14-day window)
    Only invoice 1 should be returned.
    """
    from src.services.reminder_service import get_eligible_invoices

    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        inv_eligible = _make_invoice(session, debtor, date.today() + timedelta(days=1))
        _make_invoice(session, debtor, date.today() - timedelta(days=1), status=InvoiceStatus.overdue)
        _make_invoice(session, debtor, date.today() + timedelta(days=30))
        session.commit()

        results = get_eligible_invoices(session, lookahead_days=14)
        assert len(results) == 1
        assert results[0].id == inv_eligible.id
        assert results[0].due_date == date.today() + timedelta(days=1)
    finally:
        session.close()


def test_get_eligible_excludes_paused():
    """A paused invoice within the window must NOT be returned."""
    from src.services.reminder_service import get_eligible_invoices

    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Paused Inc")
        _make_invoice(session, debtor, date.today() + timedelta(days=3), status=InvoiceStatus.paused)
        session.commit()

        results = get_eligible_invoices(session, lookahead_days=14)
        # The paused invoice should be excluded
        paused_ids = [r.id for r in results if r.status == InvoiceStatus.paused]
        assert len(paused_ids) == 0
    finally:
        session.close()


def test_get_eligible_today_is_included():
    """An invoice due *today* should be eligible (boundary case)."""
    from src.services.reminder_service import get_eligible_invoices

    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Today Corp")
        inv_today = _make_invoice(session, debtor, date.today())
        session.commit()

        results = get_eligible_invoices(session, lookahead_days=14)
        found = [r for r in results if r.id == inv_today.id]
        assert len(found) == 1
    finally:
        session.close()


def test_process_due_reminders_sends_emails():
    """process_due_reminders should call send_reminder_email for each eligible invoice."""
    from src.services.reminder_service import get_eligible_invoices

    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Process Corp")
        _make_invoice(session, debtor, date.today() + timedelta(days=2))
        session.commit()
    finally:
        session.close()

    with patch('src.services.reminder_service.send_reminder_email') as mock_send:
        from src.services.reminder_service import process_due_reminders
        process_due_reminders()
        assert mock_send.call_count >= 1
