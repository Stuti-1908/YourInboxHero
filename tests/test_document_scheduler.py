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


def _make_titled_request(session, client, title, tier):
    req = _make_overdue_request(
        session, client, escalation_tier=tier,
        escalation_started_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    req.title = title
    session.flush()
    return req


def test_document_sms_groups_all_overdue_documents_for_a_client_into_one_text():
    from unittest.mock import patch
    session = SessionLocal()
    try:
        user = _make_user(session)
        client = _make_client(session, phone="+15551234567", user_id=user.id)
        ids = [_make_titled_request(session, client, t, "sms").id for t in ("W-9", "Lease", "ID")]
        session.commit()
        user_id = user.id
    finally:
        session.close()

    with patch('src.services.ghl_service.send_sms', return_value=True) as mock_sms:
        session = SessionLocal()
        try:
            run_document_sms_reminders(session)
        finally:
            session.close()

    sent_to_this_client = [c for c in mock_sms.call_args_list if c.kwargs['contact_email'].endswith('@example.com')
                           and "3 documents" in c.kwargs["message"]]
    assert len(sent_to_this_client) == 1
    assert "3 documents" in sent_to_this_client[0].kwargs['message']

    session = SessionLocal()
    try:
        reqs = session.query(DocumentRequest).filter(DocumentRequest.id.in_(ids)).all()
        assert all(r.sms_sent_count == 1 and r.last_reminder_sent is not None for r in reqs)
        assert session.query(User).get(user_id).chases_used == 1  # one text = one chase
    finally:
        session.close()


def test_document_voice_groups_all_overdue_documents_for_a_client_into_one_call():
    from unittest.mock import patch
    session = SessionLocal()
    try:
        user = _make_user(session)
        client = _make_client(session, phone="+15559876543", voice_call_consent=True, user_id=user.id)
        ids = [_make_titled_request(session, client, t, "voice").id for t in ("Passport", "Payslip")]
        session.commit()
        user_id = user.id
        client_email = client.email
    finally:
        session.close()

    with patch('src.services.ghl_service.trigger_voice_call', return_value=True) as mock_call, \
         patch('src.services.call_window.is_within_calling_window', return_value=True):
        session = SessionLocal()
        try:
            run_document_voice_calls(session)
        finally:
            session.close()

    calls = [c for c in mock_call.call_args_list if c.kwargs['contact_email'] == client_email]
    assert len(calls) == 1
    assert 'Passport' in calls[0].kwargs['message'] and 'Payslip' in calls[0].kwargs['message']
    assert calls[0].kwargs['item_description'] == 'Passport and Payslip'

    session = SessionLocal()
    try:
        reqs = session.query(DocumentRequest).filter(DocumentRequest.id.in_(ids)).all()
        assert all(r.voice_call_count == 1 for r in reqs)
        assert session.query(User).get(user_id).chases_used == 1
    finally:
        session.close()


def test_grouped_document_sms_stays_short_whatever_the_document_count():
    from types import SimpleNamespace as NS
    from src.scheduler import _document_sms_message
    reqs = [NS(title=f"Very long document title number {i} for tax year 2026", upload_token=f"doc_{i:012d}") for i in range(10)]
    msg = _document_sms_message("Jane Smith", "Acme Bookkeeping LLC", reqs)
    assert "10 documents" in msg and "doc_000000000000" in msg
    assert len(msg) <= 306  # at most two GSM segments, regardless of count
