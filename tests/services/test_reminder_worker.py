"""Tests for the reminder worker — handle_invoice_reminder."""
import uuid
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.reminder import ReminderLog


def _make_debtor(session, name="Worker Corp"):
    d = Debtor(
        id=str(uuid.uuid4()),
        name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def _make_invoice(session, debtor, due_date=None, status=InvoiceStatus.upcoming):
    inv = Invoice(
        id=str(uuid.uuid4()),
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=1000.00,
        due_date=due_date or (date.today() + timedelta(days=5)),
        status=status,
    )
    session.add(inv)
    session.flush()
    return inv


def test_handle_invoice_reminder_success():
    """Worker should send email, log 'sent' to reminder_log, and stamp last_reminder_sent."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        inv = _make_invoice(session, debtor)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    with patch('src.services.reminder_worker.send_reminder_email') as mock_send:
        from src.services.reminder_worker import handle_invoice_reminder
        handle_invoice_reminder(inv_id)
        mock_send.assert_called_once()

    # Verify reminder_log was written
    session = SessionLocal()
    try:
        logs = session.query(ReminderLog).filter(ReminderLog.invoice_id == inv_id).all()
        assert len(logs) == 1
        assert logs[0].status.value == 'sent'
        assert logs[0].channel.value == 'email'
    finally:
        session.close()


def test_handle_invoice_reminder_failure_logs_failed():
    """If email sending fails, worker should log 'failed' status."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Fail Corp")
        inv = _make_invoice(session, debtor)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    with patch('src.services.reminder_worker.send_reminder_email', side_effect=Exception('SMTP down')):
        from src.services.reminder_worker import handle_invoice_reminder
        handle_invoice_reminder(inv_id)

    session = SessionLocal()
    try:
        logs = session.query(ReminderLog).filter(ReminderLog.invoice_id == inv_id).all()
        assert len(logs) == 1
        assert logs[0].status.value == 'failed'
    finally:
        session.close()


def test_handle_invoice_reminder_not_found():
    """Worker should raise ValueError for a non-existent invoice."""
    import pytest
    from src.services.reminder_worker import handle_invoice_reminder
    with pytest.raises(ValueError, match='not found'):
        handle_invoice_reminder('nonexistent-id-12345')


def test_consume_queue_function_exists():
    """The Service Bus consumer entry point must exist and expose a callable main()."""
    import importlib
    mod = importlib.import_module('src.functions.consume_queue')
    assert hasattr(mod, 'main')
    assert callable(mod.main)
