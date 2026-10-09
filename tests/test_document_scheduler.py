"""Tests for scheduler.py's document-request escalation/SMS/voice sweeps.
Mirrors tests/test_scheduler.py (the invoice version) exactly, including
the timezone-crash regression tests -- the document escalation functions
share the same _as_aware_utc helper and datetime-comparison patterns, so
they're exposed to the identical SQLite-naive-datetime bug class.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest
from src.models.user import User
from src.scheduler import run_document_escalation_sweep, run_document_sms_reminders, run_document_voice_calls


def _make_client(session, name="Doc Scheduler Test Corp", phone=None, voice_call_consent=False, user_id='test-id'):
    c = DocumentClient(
        user_id=user_id, id=str(uuid.uuid4()), name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        phone=phone, voice_call_consent=voice_call_consent,
    )
    session.add(c)
    session.flush()
    return c


def _make_user(session, subscription_status="active", chases_limit=750, chases_used=0):
    u = User(
        id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="pwd", company_name="Doc Scheduler Test User Co",
        subscription_plan="scale", subscription_status=subscription_status,
        chases_limit=chases_limit, chases_used=chases_used,
    )
    session.add(u)
    session.flush()
    return u


def _make_overdue_request(session, client, escalation_tier, escalation_started_at, last_reminder_sent=None):
    req = DocumentRequest(
        id=str(uuid.uuid4()), user_id=client.user_id, client_id=client.id,
        title="W-9 Tax Form", due_date=date.today() - timedelta(days=20),
        status="overdue", escalation_tier=escalation_tier,
        escalation_started_at=escalation_started_at, last_reminder_sent=last_reminder_sent,
    )
    session.add(req)
    session.flush()
    return req


def test_document_escalation_sweep_does_not_crash_on_multi_day_old_request():
    session = SessionLocal()
    try:
        client = _make_client(session)
        started = datetime.now(timezone.utc) - timedelta(days=20)
        req = _make_overdue_request(session, client, escalation_tier="email", escalation_started_at=started)
        session.commit()
        req_id = req.id
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_escalation_sweep(session)  # must not raise
    finally:
        session.close()

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        assert refreshed.escalation_tier == "sms"
    finally:
        session.close()


def test_document_sms_reminders_does_not_crash_reading_last_reminder_sent():
    session = SessionLocal()
    try:
        client = _make_client(session, phone="+15551234567")
        last_sent = datetime.now(timezone.utc) - timedelta(days=3)
        _make_overdue_request(
            session, client, escalation_tier="sms",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=5),
            last_reminder_sent=last_sent,
        )
        session.commit()
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_sms_reminders(session)  # must not raise
    finally:
        session.close()


def test_document_voice_calls_does_not_crash_reading_last_reminder_sent():
    session = SessionLocal()
    try:
        client = _make_client(session, phone="+15551234567", voice_call_consent=True)
        last_sent = datetime.now(timezone.utc) - timedelta(days=5)
        _make_overdue_request(
            session, client, escalation_tier="voice",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=10),
            last_reminder_sent=last_sent,
        )
        session.commit()
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_voice_calls(session)  # must not raise
    finally:
        session.close()


def test_document_voice_calls_skips_client_without_consent():
    """Same TCPA-style consent gate as invoices: a client with a phone
    number but no recorded voice_call_consent must never be called."""
    session = SessionLocal()
    try:
        client = _make_client(session, phone="+15551234567", voice_call_consent=False)
        req = _make_overdue_request(
            session, client, escalation_tier="voice",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        session.commit()
        req_id = req.id
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_voice_calls(session)
    finally:
        session.close()

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        assert refreshed.voice_call_count == 0
        assert refreshed.last_reminder_sent is None
    finally:
        session.close()


def test_document_sms_reminders_skips_client_of_cancelled_subscription():
    session = SessionLocal()
    try:
        user = _make_user(session, subscription_status="cancelled")
        client = _make_client(session, phone="+15551234567", user_id=user.id)
        req = _make_overdue_request(
            session, client, escalation_tier="sms",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        session.commit()
        req_id = req.id
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_sms_reminders(session)
    finally:
        session.close()

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        assert refreshed.sms_sent_count == 0
        assert refreshed.last_reminder_sent is None
    finally:
        session.close()


def test_document_voice_calls_skips_client_of_past_due_subscription():
    session = SessionLocal()
    try:
        user = _make_user(session, subscription_status="past_due")
        client = _make_client(session, phone="+15551234567", voice_call_consent=True, user_id=user.id)
        req = _make_overdue_request(
            session, client, escalation_tier="voice",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        session.commit()
        req_id = req.id
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_voice_calls(session)
    finally:
        session.close()

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        assert refreshed.voice_call_count == 0
    finally:
        session.close()


def test_document_sms_reminders_skips_client_without_phone():
    session = SessionLocal()
    try:
        client = _make_client(session, phone=None)
        req = _make_overdue_request(
            session, client, escalation_tier="sms",
            escalation_started_at=datetime.now(timezone.utc) - timedelta(days=5),
        )
        session.commit()
        req_id = req.id
    finally:
        session.close()

    session = SessionLocal()
    try:
        run_document_sms_reminders(session)
    finally:
        session.close()

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        assert refreshed.sms_sent_count == 0
    finally:
        session.close()
