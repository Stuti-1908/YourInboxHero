"""Tests for the manual reminder endpoint — POST /reminder/manual."""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.app import app
from src.auth import get_current_user
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.user import User

client = TestClient(app)


def test_manual_reminder_404():
    # Use a valid UUID format that does not exist in the DB
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.post(f'/reminders/{fake_id}/send-now', json={})
    assert resp.status_code == 404


def test_manual_reminder_success():
    debtor_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        debtor = Debtor(
            user_id='test-id', id=debtor_id, name="Success Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business",
        )
        session.add(debtor)
        inv = Invoice(
            id=str(uuid.uuid4()), user_id='test-id', debtor_id=debtor_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=500.00,
            due_date=date.today() + timedelta(days=5), status=InvoiceStatus.upcoming,
        )
        session.add(inv)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    with patch('src.api.reminder_manual.send_reminder_email') as mock_send:
        resp = client.post(f'/reminders/{inv_id}/send-now', json={})
        assert resp.status_code == 200
        assert resp.json()['detail'] == 'Reminder sent'
        mock_send.assert_called_once()

    session = SessionLocal()
    try:
        refreshed = session.query(Invoice).filter(Invoice.id == inv_id).first()
        assert refreshed.last_reminder_sent is not None
    finally:
        session.close()


def test_manual_reminder_rejects_non_business_debtor():
    """Personal/individual debtors are never automated -- per the plan's
    legal guardrail, manual sends are gated the same way."""
    debtor_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        debtor = Debtor(
            user_id='test-id', id=debtor_id, name="Individual Debtor",
            email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="individual",
        )
        session.add(debtor)
        inv = Invoice(
            id=str(uuid.uuid4()), user_id='test-id', debtor_id=debtor_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=500.00,
            due_date=date.today() + timedelta(days=5), status=InvoiceStatus.upcoming,
        )
        session.add(inv)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    with patch('src.api.reminder_manual.send_reminder_email') as mock_send:
        resp = client.post(f'/reminders/{inv_id}/send-now', json={})
        assert resp.status_code == 400
        mock_send.assert_not_called()


def test_manual_reminder_rejects_past_due_invoice():
    """Overdue invoices never get automated email per the legal guardrail
    -- the manual trigger must enforce this too, not just the daily sweep."""
    debtor_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        debtor = Debtor(
            user_id='test-id', id=debtor_id, name="Past Due Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business",
        )
        session.add(debtor)
        inv = Invoice(
            id=str(uuid.uuid4()), user_id='test-id', debtor_id=debtor_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=500.00,
            due_date=date.today() - timedelta(days=1), status=InvoiceStatus.overdue,
        )
        session.add(inv)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    with patch('src.api.reminder_manual.send_reminder_email') as mock_send:
        resp = client.post(f'/reminders/{inv_id}/send-now', json={})
        assert resp.status_code == 400
        mock_send.assert_not_called()


def test_manual_reminder_blocked_at_chase_limit():
    """The user-facing manual trigger must return 402 (not a generic 500 or
    silent no-op) once the plan's monthly reminder allowance is exhausted.

    Overrides get_current_user directly (rather than relying on conftest's
    global override, which always returns a fixed chases_limit/chases_used
    disconnected from the DB) so this test can actually exercise an
    at-the-limit account.
    """
    debtor_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        debtor = Debtor(
            user_id='test-id', id=debtor_id, name="Limit Test Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business",
        )
        session.add(debtor)
        inv = Invoice(
            id=str(uuid.uuid4()), user_id='test-id', debtor_id=debtor_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=500.00,
            due_date=date.today() + timedelta(days=5), status=InvoiceStatus.upcoming,
        )
        session.add(inv)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    def at_limit_user():
        return User(
            id='test-id', username='testuser', company_name='Test Corp',
            subscription_status='active', subscription_plan='growth',
            chases_limit=3, chases_used=3,
        )

    original_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = at_limit_user
    try:
        with patch('src.api.reminder_manual.send_reminder_email') as mock_send:
            resp = client.post(f'/reminders/{inv_id}/send-now', json={})
            assert resp.status_code == 402
            mock_send.assert_not_called()
    finally:
        if original_override:
            app.dependency_overrides[get_current_user] = original_override
        else:
            app.dependency_overrides.pop(get_current_user, None)
