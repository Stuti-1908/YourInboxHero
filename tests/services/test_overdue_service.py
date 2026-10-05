"""Tests for overdue_service.transition_overdue and mark_overdue Azure Function."""
import uuid
from datetime import date, timedelta

from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus


def _make_debtor(session, name="Overdue Corp"):
    d = Debtor(user_id='test-id', 
        id=str(uuid.uuid4()),
        name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def _make_invoice(session, debtor, due_date, status=InvoiceStatus.upcoming):
    inv = Invoice(
        id=str(uuid.uuid4()),
        user_id=debtor.user_id,
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=500.00,
        due_date=due_date,
        status=status,
    )
    session.add(inv)
    session.flush()
    return inv


def test_transition_overdue_marks_past_due():
    """Invoices with due_date < today and status upcoming/due → overdue."""
    from src.services.overdue_service import transition_overdue

    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        inv_past = _make_invoice(session, debtor, date.today() - timedelta(days=1))
        inv_future = _make_invoice(session, debtor, date.today() + timedelta(days=5))
        session.commit()

        count = transition_overdue(session)

        session.refresh(inv_past)
        session.refresh(inv_future)
        assert inv_past.status == InvoiceStatus.overdue
        assert inv_future.status == InvoiceStatus.upcoming
        assert count >= 1
    finally:
        session.close()


def test_transition_overdue_skips_already_overdue():
    """An invoice already marked overdue should not be double-processed."""
    from src.services.overdue_service import transition_overdue

    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="AlreadyOverdue Corp")
        inv = _make_invoice(session, debtor, date.today() - timedelta(days=3), status=InvoiceStatus.overdue)
        session.commit()

        count = transition_overdue(session)

        session.refresh(inv)
        assert inv.status == InvoiceStatus.overdue
        # The already-overdue invoice should not be counted in the transition
        assert count == 0
    finally:
        session.close()


def test_transition_overdue_handles_due_status():
    """Invoices with status 'due' and past due_date should also be transitioned."""
    from src.services.overdue_service import transition_overdue

    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Due Corp")
        inv = _make_invoice(session, debtor, date.today() - timedelta(days=1), status=InvoiceStatus.due)
        session.commit()

        count = transition_overdue(session)

        session.refresh(inv)
        assert inv.status == InvoiceStatus.overdue
        assert count >= 1
    finally:
        session.close()


def test_mark_overdue_function_exists():
    """The Azure Function entry point must exist and expose a callable main()."""
    import importlib
    mod = importlib.import_module('src.functions.mark_overdue')
    assert hasattr(mod, 'main')
    assert callable(mod.main)
