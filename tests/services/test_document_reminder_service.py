"""Tests for document_reminder_service.get_eligible_document_requests —
mirrors test_reminder_service.py for invoices."""
import uuid
from datetime import date, timedelta

from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest


def _make_client(session, name="Doc Reminder Co", user_id='test-id'):
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


def test_get_eligible_returns_only_pending_within_window():
    from src.services.document_reminder_service import get_eligible_document_requests

    session = SessionLocal()
    try:
        client = _make_client(session)
        eligible = _make_request(session, client, date.today() + timedelta(days=1))
        _make_request(session, client, date.today() - timedelta(days=1), status="overdue")
        _make_request(session, client, date.today() + timedelta(days=30))
        session.commit()

        results = get_eligible_document_requests(session, lookahead_days=14)
        results = [r for r in results if r.client_id == client.id]
        assert len(results) == 1
        assert results[0].id == eligible.id
    finally:
        session.close()


def test_get_eligible_excludes_submitted_and_approved():
    from src.services.document_reminder_service import get_eligible_document_requests

    session = SessionLocal()
    try:
        client = _make_client(session, name="Resolved Doc Co")
        submitted = _make_request(session, client, date.today() + timedelta(days=3), status="submitted")
        approved = _make_request(session, client, date.today() + timedelta(days=3), status="approved")
        session.commit()

        results = get_eligible_document_requests(session, lookahead_days=14)
        result_ids = {r.id for r in results}
        assert submitted.id not in result_ids
        assert approved.id not in result_ids
    finally:
        session.close()


def test_get_eligible_today_is_included():
    from src.services.document_reminder_service import get_eligible_document_requests

    session = SessionLocal()
    try:
        client = _make_client(session, name="Due Today Doc Co")
        req_today = _make_request(session, client, date.today())
        session.commit()

        results = get_eligible_document_requests(session, lookahead_days=14)
        found = [r for r in results if r.id == req_today.id]
        assert len(found) == 1
    finally:
        session.close()
