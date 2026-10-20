"""Tests for document_reminder_worker.handle_document_reminder — mirrors
test_reminder_worker.py for invoices. No ReminderLog assertions here:
that table's invoice_id is NOT NULL/FK'd to invoice specifically, so
document sends aren't logged there (see document_reminder_worker.py's
module docstring) -- last_reminder_sent/chases_used are the equivalent
coverage.
"""
import uuid
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest


def _make_client(session, name="Doc Worker Co"):
    c = DocumentClient(
        user_id='test-id', id=str(uuid.uuid4()), name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
    )
    session.add(c)
    session.flush()
    return c


def _make_request(session, client, due_date=None, status="pending"):
    req = DocumentRequest(
        id=str(uuid.uuid4()), user_id=client.user_id, client_id=client.id,
        title="W-9 Tax Form", due_date=due_date or (date.today() + timedelta(days=5)),
        status=status,
    )
    session.add(req)
    session.flush()
    return req


def test_handle_document_reminder_success():
    session = SessionLocal()
    try:
        client = _make_client(session)
        req = _make_request(session, client)
        session.commit()
        req_id = req.id
    finally:
        session.close()

    with patch('src.services.document_reminder_worker.send_document_request_email') as mock_send:
        from src.services.document_reminder_worker import handle_document_reminder
        handle_document_reminder(req_id)
        mock_send.assert_called_once()

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        assert refreshed.last_reminder_sent is not None
    finally:
        session.close()


def test_handle_document_reminder_failure_propagates():
    """Unlike the invoice worker (which logs failed sends to
    ReminderLog), a failed document email send has nowhere to be
    recorded, so handle_document_reminder re-raises -- the caller
    (process_due_document_reminders) counts it as failed via its own
    try/except, same end result as the invoice path's logged failure."""
    session = SessionLocal()
    try:
        client = _make_client(session, name="Fail Doc Co")
        req = _make_request(session, client)
        session.commit()
        req_id = req.id
    finally:
        session.close()

    with patch('src.services.document_reminder_worker.send_document_request_email', side_effect=Exception('Resend down')):
        from src.services.document_reminder_worker import handle_document_reminder
        with pytest.raises(Exception, match='Resend down'):
            handle_document_reminder(req_id)

    session = SessionLocal()
    try:
        refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
        # A failed attempt must not be stamped as sent.
        assert refreshed.last_reminder_sent is None
    finally:
        session.close()


def test_handle_document_reminder_not_found():
    from src.services.document_reminder_worker import handle_document_reminder
    with pytest.raises(ValueError, match='not found'):
        handle_document_reminder('nonexistent-id-12345')


def test_handle_document_reminder_increments_chases_used():
    from src.models.user import User

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id='test-id').first()
        before = user.chases_used or 0
        client = _make_client(session)
        req = _make_request(session, client)
        session.commit()
        req_id = req.id
    finally:
        session.close()

    with patch('src.services.document_reminder_worker.send_document_request_email'):
        from src.services.document_reminder_worker import handle_document_reminder
        handle_document_reminder(req_id)

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id='test-id').first()
        assert user.chases_used == before + 1
    finally:
        session.close()


def test_handle_document_reminder_blocked_at_chase_limit():
    from src.models.user import User
    from src.services.document_reminder_worker import handle_document_reminder, ChaseLimitReached

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id='test-id').first()
        original_limit, original_used = user.chases_limit, user.chases_used
        user.chases_limit = 5
        user.chases_used = 5
        client = _make_client(session, name="At Limit Doc Co")
        req = _make_request(session, client)
        session.commit()
        req_id = req.id
    finally:
        session.close()

    try:
        with patch('src.services.document_reminder_worker.send_document_request_email') as mock_send:
            with pytest.raises(ChaseLimitReached):
                handle_document_reminder(req_id)
            mock_send.assert_not_called()

        session = SessionLocal()
        try:
            refreshed = session.query(DocumentRequest).filter(DocumentRequest.id == req_id).first()
            assert refreshed.last_reminder_sent is None
            user = session.query(User).filter_by(id='test-id').first()
            assert user.chases_used == 5
        finally:
            session.close()
    finally:
        session = SessionLocal()
        try:
            user = session.query(User).filter_by(id='test-id').first()
            user.chases_limit = original_limit
            user.chases_used = original_used
            session.commit()
        finally:
            session.close()


def test_process_due_document_reminders_sends_one_email_per_client():
    from src.models.user import User
    session = SessionLocal()
    try:
        user = User(id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
                    hashed_password="x", subscription_plan="scale", subscription_status="active",
                    chases_limit=750, chases_used=0)
        session.add(user)
        session.flush()
        c = DocumentClient(user_id=user.id, id=str(uuid.uuid4()), name="Grouped",
                           email=f"{uuid.uuid4().hex[:8]}@example.com")
        session.add(c)
        session.flush()
        ids = []
        for title in ("A", "B", "C"):
            r = DocumentRequest(id=str(uuid.uuid4()), user_id=user.id, client_id=c.id, title=title,
                                due_date=date.today() + timedelta(days=2), status="pending")
            session.add(r)
            ids.append(r.id)
        session.commit()
        user_id = user.id
    finally:
        session.close()

    batches = []
    with patch('src.services.document_reminder_worker.send_document_request_email',
               side_effect=lambda docs: batches.append({d.id for d in docs})), \
         patch('src.feature_flags.reminders_enabled', return_value=True):
        from src.services.document_reminder_service import process_due_document_reminders
        process_due_document_reminders()

    assert [b for b in batches if b & set(ids)] == [set(ids)]

    session = SessionLocal()
    try:
        assert session.query(User).get(user_id).chases_used == 1
        assert all(r.last_reminder_sent is not None
                   for r in session.query(DocumentRequest).filter(DocumentRequest.id.in_(ids)))
    finally:
        session.close()
