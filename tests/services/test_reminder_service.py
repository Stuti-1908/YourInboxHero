"""Tests for reminder_service — get_eligible_invoices and process_due_reminders.

Each test creates its own isolated data using unique UUIDs and debtor emails.
"""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus


def _make_debtor(session, name="Acme Corp"):
    d = Debtor(user_id='test-id', 
        id=str(uuid.uuid4()),
        name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
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

        # Query only invoices for this debtor to isolate from other tests
        results = get_eligible_invoices(session, lookahead_days=14)
        # Filter to only invoices belonging to our test debtor
        results = [r for r in results if r.debtor_id == debtor.id]
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
        paused_inv = _make_invoice(session, debtor, date.today() + timedelta(days=3), status=InvoiceStatus.paused)
        session.commit()

        results = get_eligible_invoices(session, lookahead_days=14)
        # The paused invoice should never appear
        paused_ids = [r.id for r in results if r.id == paused_inv.id]
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


def test_process_due_reminders_enqueues(monkeypatch):
    """process_due_reminders should call enqueue_reminder for each eligible invoice."""
    # Ensure feature flag is on
    monkeypatch.setenv('REMINDERS_ENABLED', 'true')

    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Process Corp")
        _make_invoice(session, debtor, date.today() + timedelta(days=2))
        session.commit()
    finally:
        session.close()

    with patch('src.services.queue.enqueue_reminder') as mock_enqueue:
        from src.services.reminder_service import process_due_reminders
        process_due_reminders()
        assert mock_enqueue.call_count >= 1

