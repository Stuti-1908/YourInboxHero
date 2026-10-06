"""Tests for the reminder worker — handle_invoice_reminder."""
import uuid
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.reminder import ReminderLog


def _make_debtor(session, name="Worker Corp"):
    d = Debtor(user_id='test-id',
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
        user_id=debtor.user_id,
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


def test_handle_invoice_reminder_increments_chases_used():
    """A successful send must increment the owning user's chases_used."""
    from src.models.user import User

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id='test-id').first()
        before = user.chases_used or 0
        debtor = _make_debtor(session)
        inv = _make_invoice(session, debtor)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    with patch('src.services.reminder_worker.send_reminder_email'):
        from src.services.reminder_worker import handle_invoice_reminder
        handle_invoice_reminder(inv_id)

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id='test-id').first()
        assert user.chases_used == before + 1
    finally:
        session.close()


def test_handle_invoice_reminder_blocked_at_chase_limit():
    """Once chases_used reaches chases_limit, no further send is attempted
    and no reminder_log entry or usage increment occurs -- the attempt
    simply never happened, so a plan upgrade next cycle picks up cleanly."""
    from src.models.user import User
    from src.services.reminder_worker import handle_invoice_reminder, ChaseLimitReached

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(id='test-id').first()
        original_limit, original_used = user.chases_limit, user.chases_used
        user.chases_limit = 5
        user.chases_used = 5
        debtor = _make_debtor(session, name="At Limit Corp")
        inv = _make_invoice(session, debtor)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    try:
        with patch('src.services.reminder_worker.send_reminder_email') as mock_send:
            with pytest.raises(ChaseLimitReached):
                handle_invoice_reminder(inv_id)
            mock_send.assert_not_called()

        session = SessionLocal()
        try:
            logs = session.query(ReminderLog).filter(ReminderLog.invoice_id == inv_id).all()
            assert len(logs) == 0
            user = session.query(User).filter_by(id='test-id').first()
            assert user.chases_used == 5
        finally:
            session.close()
    finally:
        # Restore the shared test-id fixture for other tests in the suite.
        session = SessionLocal()
        try:
            user = session.query(User).filter_by(id='test-id').first()
            user.chases_limit = original_limit
            user.chases_used = original_used
            session.commit()
        finally:
            session.close()
