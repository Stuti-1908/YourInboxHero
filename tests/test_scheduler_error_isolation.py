"""Tests for H3/H4 scheduler hardening:
- Per-invoice commits so one failing send doesn't roll back or block
  earlier/later successful sends in the same sweep.
- The daily-sweep-ran-today tracking used for the startup catch-up check.

GHL calls are mocked throughout (unlike some older scheduler tests) so
these don't depend on network access or real credentials.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.sweep_run import SweepRun
from src.scheduler import (
    run_sms_reminders, _mark_sweep_run_today, SWEEP_RUN_ID,
    run_daily_sweep, run_catch_up_sweep_if_needed,
)


def _make_debtor(session, phone="+15551234567"):
    d = Debtor(
        user_id='test-id', id=str(uuid.uuid4()), name="Isolation Test Corp",
        email=f"{uuid.uuid4().hex[:8]}@example.com", phone=phone,
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def _make_sms_invoice(session, debtor):
    inv = Invoice(
        id=str(uuid.uuid4()), user_id=debtor.user_id, debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=500.00,
        due_date=date.today() - timedelta(days=20), status=InvoiceStatus.overdue,
        escalation_tier="sms", escalation_started_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    session.add(inv)
    session.flush()
    return inv


def test_one_failing_sms_send_does_not_block_others_in_same_sweep():
    """A GHL exception on one invoice must not prevent a later invoice in
    the same loop from being sent and recorded."""
    phone_a, phone_b = "+15550000001", "+15550000002"
    session = SessionLocal()
    try:
        debtor_a = _make_debtor(session, phone=phone_a)
        debtor_b = _make_debtor(session, phone=phone_b)
        inv_a = _make_sms_invoice(session, debtor_a)
        inv_b = _make_sms_invoice(session, debtor_b)
        session.commit()
        inv_a_id, inv_b_id = inv_a.id, inv_b.id
    finally:
        session.close()

    # Fail only for inv_a's phone number specifically — other leftover
    # SMS-tier invoices may exist in the shared test DB from other test
    # modules in the same run, and must not affect this assertion.
    def flaky_send_sms(phone, *args, **kwargs):
        if phone == phone_a:
            raise RuntimeError("simulated GHL outage")
        return True

    session = SessionLocal()
    try:
        with patch('src.services.ghl_service.send_sms', side_effect=flaky_send_sms):
            run_sms_reminders(session)
    finally:
        session.close()

    session = SessionLocal()
    try:
        invoices = session.query(Invoice).filter(Invoice.id.in_([inv_a_id, inv_b_id])).all()
        # Exactly one of the two must show a successful send recorded —
        # the failing one stays untouched, the other must not be blocked.
        sent = [i for i in invoices if i.sms_sent_count > 0]
        failed = [i for i in invoices if i.sms_sent_count == 0]
        assert len(sent) == 1
        assert len(failed) == 1
    finally:
        session.close()


def test_mark_sweep_run_today_is_idempotent():
    session = SessionLocal()
    try:
        _mark_sweep_run_today(session)
        _mark_sweep_run_today(session)  # must not raise on the second call
        row = session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).first()
        assert row is not None
        assert row.last_run_date == datetime.now(timezone.utc).date()
    finally:
        session.close()


def test_run_daily_sweep_marks_sweep_run_even_if_a_step_raises():
    """H4: one step (e.g. overdue_transition) raising must not prevent
    later steps from running, and must not prevent _mark_sweep_run_today
    from recording that the sweep happened -- otherwise a single bad step
    would make the startup catch-up check re-run the whole sweep forever."""
    session = SessionLocal()
    try:
        session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).delete()
        session.commit()
    finally:
        session.close()

    with patch('src.scheduler.transition_overdue', side_effect=RuntimeError("boom")):
        run_daily_sweep()  # must not raise

    session = SessionLocal()
    try:
        row = session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).first()
        assert row is not None
        assert row.last_run_date == datetime.now(timezone.utc).date()
    finally:
        session.close()


def test_run_catch_up_sweep_skips_when_already_run_today():
    """If today's scheduled sweep already ran, the startup catch-up check
    must not trigger a second run."""
    session = SessionLocal()
    try:
        _mark_sweep_run_today(session)
    finally:
        session.close()

    with patch('src.scheduler.run_daily_sweep') as mock_sweep:
        run_catch_up_sweep_if_needed()
        mock_sweep.assert_not_called()


def test_run_catch_up_sweep_runs_when_not_yet_run_today():
    """If no sweep has run today (e.g. container was down at 08:00 UTC),
    the startup catch-up check must trigger one immediately."""
    session = SessionLocal()
    try:
        session.query(SweepRun).filter(SweepRun.id == SWEEP_RUN_ID).delete()
        session.commit()
    finally:
        session.close()

    with patch('src.scheduler.run_daily_sweep') as mock_sweep:
        run_catch_up_sweep_if_needed()
        mock_sweep.assert_called_once()
