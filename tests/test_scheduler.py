"""Tests for src/scheduler.py's escalation/SMS/voice sweeps.

The real bug this guards against: several TIMESTAMP columns used to be
naive (no timezone), but scheduler.py compares them against
datetime.now(timezone.utc) (aware). On Postgres that raises
"can't subtract offset-naive and offset-aware datetimes" -- silently
caught and logged per-step in run_daily_sweep, so escalation/SMS/voice
reminders stopped actually running for any invoice more than a day old,
with nothing surfacing the failure. These tests write and re-read an
invoice through the real DB session (not a raw in-memory object) so the
column's actual stored type is exercised, the same way production data
flows through it.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.scheduler import run_escalation_sweep, run_sms_reminders, run_voice_calls


def _make_debtor(session, name="Scheduler Test Corp", phone=None):
    d = Debtor(
        user_id='test-id',
        id=str(uuid.uuid4()),
        name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        phone=phone,
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def _make_overdue_invoice(session, debtor, escalation_tier, escalation_started_at, last_reminder_sent=None):
    inv = Invoice(
        id=str(uuid.uuid4()),
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=500.00,
        due_date=date.today() - timedelta(days=20),
        status=InvoiceStatus.overdue,
        escalation_tier=escalation_tier,
        escalation_started_at=escalation_started_at,
        last_reminder_sent=last_reminder_sent,
    )
    session.add(inv)
    session.flush()
    return inv


def test_escalation_sweep_does_not_crash_on_multi_day_old_invoice():
    """This is the exact crash scenario: an invoice that has already been
    sitting in the 'email' tier for several days (escalation_started_at is
    several days in the past, round-tripped through the real DB column)
    must be evaluated for escalation without raising."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        started = datetime.now(timezone.utc) - timedelta(days=20)
        inv = _make_overdue_invoice(session, debtor, escalation_tier="email", escalation_started_at=started)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    session = SessionLocal()
    try:
        # Must not raise TypeError: can't subtract offset-naive and
        # offset-aware datetimes.
        run_escalation_sweep(session)
    finally:
        session.close()

    session = SessionLocal()
    try:
        refreshed = session.query(Invoice).filter(Invoice.id == inv_id).first()
        # 20 days in 'email' tier is well past EMAIL_TO_SMS_DAYS, so it
        # should have escalated.
        assert refreshed.escalation_tier == "sms"
    finally:
        session.close()


def test_sms_reminders_does_not_crash_reading_last_reminder_sent():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, phone="+15551234567")
        last_sent = datetime.now(timezone.utc) - timedelta(days=3)
        inv = _make_overdue_invoice(
            session, debtor, escalation_tier="sms",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=5),
            last_reminder_sent=last_sent,
        )
        session.commit()
    finally:
        session.close()

    session = SessionLocal()
    try:
        # Must not raise comparing last_reminder_sent (aware-after-fix)
        # against today_start (aware).
        run_sms_reminders(session)
    finally:
        session.close()


def test_voice_calls_does_not_crash_reading_last_reminder_sent():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, phone="+15551234567")
        last_sent = datetime.now(timezone.utc) - timedelta(days=5)
        inv = _make_overdue_invoice(
            session, debtor, escalation_tier="voice",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=10),
            last_reminder_sent=last_sent,
        )
        session.commit()
    finally:
        session.close()

    session = SessionLocal()
    try:
        # Must not raise comparing last_reminder_sent against
        # datetime.now(timezone.utc) at scheduler.py's "only call once
        # every 3 days" check.
        run_voice_calls(session)
    finally:
        session.close()
