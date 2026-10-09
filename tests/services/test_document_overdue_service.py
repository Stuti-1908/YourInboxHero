"""Tests for document_overdue_service.transition_overdue — mirrors
test_overdue_service.py for invoices."""
import uuid
from datetime import date, timedelta

from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest


def _make_client(session, name="Doc Overdue Co", user_id='test-id'):
    c = DocumentClient(
        user_id=user_id, id=str(uuid.uuid4()), name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
    )
    session.add(c)
    session.flush()
    return c


def _make_request(session, client, due_date, status="pending"):
    req = DocumentRequest(
        id=str(uuid.uuid4()), user_id=client.user_id, client_id=client.id,
        title="W-9 Tax Form", due_date=due_date, status=status,
    )
    session.add(req)
    session.flush()
    return req


def test_transition_overdue_marks_past_due_pending_requests():
    from src.services.document_overdue_service import transition_overdue

    session = SessionLocal()
    try:
        client = _make_client(session)
        req_past = _make_request(session, client, date.today() - timedelta(days=1))
        req_future = _make_request(session, client, date.today() + timedelta(days=5))
        session.commit()

        count = transition_overdue(session)

        session.refresh(req_past)
        session.refresh(req_future)
        assert req_past.status == "overdue"
        assert req_future.status == "pending"
        assert count >= 1
    finally:
        session.close()


def test_transition_overdue_skips_already_overdue():
    from src.services.document_overdue_service import transition_overdue

    session = SessionLocal()
    try:
        client = _make_client(session, name="Already Overdue Doc Co")
        req = _make_request(session, client, date.today() - timedelta(days=3), status="overdue")
        session.commit()

        count = transition_overdue(session)

        session.refresh(req)
        assert req.status == "overdue"
        assert count == 0
    finally:
        session.close()


def test_transition_overdue_does_not_touch_submitted_or_approved():
    """A submitted/approved request past its due_date must stay as-is --
    it's already resolved, not something to chase."""
    from src.services.document_overdue_service import transition_overdue

    session = SessionLocal()
    try:
        client = _make_client(session, name="Resolved Doc Co")
        submitted = _make_request(session, client, date.today() - timedelta(days=5), status="submitted")
        approved = _make_request(session, client, date.today() - timedelta(days=5), status="approved")
        session.commit()

        transition_overdue(session)

        session.refresh(submitted)
        session.refresh(approved)
        assert submitted.status == "submitted"
        assert approved.status == "approved"
    finally:
        session.close()
