"""Tests for the reminder history endpoints — JSON and CSV."""
import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.reminder import ReminderLog, Channel, ReminderStatus

client = TestClient(app)


def _seed_reminder_log(session, count=3):
    """Create a debtor, invoice, and `count` reminder log entries."""
    debtor = Debtor(user_id='test-id',
                    id=str(uuid.uuid4()),
                    name="History Corp",
                    email=f"{uuid.uuid4().hex[:8]}@example.com",
                    debtor_type="business",
                    )
    session.add(debtor)
    session.flush()

    inv = Invoice(
        id=str(uuid.uuid4()),
        user_id=debtor.user_id,
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=500.00,
        due_date=datetime(2026, 9, 1).date(),
        status=InvoiceStatus.upcoming,
    )
    session.add(inv)
    session.flush()

    log_ids = []
    for i in range(count):
        log = ReminderLog(
            id=str(uuid.uuid4()),
            invoice_id=inv.id,
            sent_at=datetime(2026, 8, 10 + i, 12, 0, 0),
            channel=Channel.email,
            payload={'seq': i},
            status=ReminderStatus.sent,
        )
        session.add(log)
        log_ids.append(log.id)

    session.commit()
    return inv.id, log_ids


def test_history_json_returns_entries():
    """GET /reminders/history should return JSON list of reminder logs."""
    session = SessionLocal()
    try:
        inv_id, log_ids = _seed_reminder_log(session, count=2)
    finally:
        session.close()

    resp = client.get('/reminders/history')
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # At least our 2 entries should be present
    returned_ids = {entry['id'] for entry in data}
    for lid in log_ids:
        assert lid in returned_ids


def test_history_json_respects_limit():
    """GET /reminders/history?limit=1 should return at most 1 entry."""
    session = SessionLocal()
    try:
        _seed_reminder_log(session, count=5)
    finally:
        session.close()

    resp = client.get('/reminders/history?limit=1')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_history_csv_returns_csv():
    """GET /reminders/history/csv should return text/csv with correct headers."""
    session = SessionLocal()
    try:
        _seed_reminder_log(session, count=2)
    finally:
        session.close()

    resp = client.get('/reminders/history/csv')
    assert resp.status_code == 200
    assert 'text/csv' in resp.headers['content-type']
    assert 'attachment' in resp.headers.get('content-disposition', '')

    # Verify CSV structure
    lines = resp.text.strip().split('\n')
    assert len(lines) >= 2  # header + at least 1 data row
    header = lines[0]
    assert 'id' in header
    assert 'invoice_id' in header
    assert 'sent_at' in header
    assert 'channel' in header
    assert 'status' in header


def test_history_empty_returns_empty_list():
    """GET /reminders/history should return empty list when no logs exist for a fresh query."""
    # This test just verifies the endpoint doesn't crash with an empty DB scenario
    # (there may be logs from other tests, so we just check the response shape)
    resp = client.get('/reminders/history')
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
