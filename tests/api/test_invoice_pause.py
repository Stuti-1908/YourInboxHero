"""Tests for the invoice pause endpoint — POST /invoice/{id}/pause."""
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus

client = TestClient(app)


def _make_debtor(session, name="Pause Corp"):
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
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=750.00,
        due_date=due_date,
        status=status,
    )
    session.add(inv)
    session.flush()
    return inv


def test_pause_invoice_404():
    """Pausing a non-existent invoice returns 404."""
    fake_id = str(uuid.uuid4())
    resp = client.post(f'/invoice/{fake_id}/pause')
    assert resp.status_code == 404


def test_pause_upcoming_invoice_200():
    """Pausing an upcoming invoice succeeds and changes status to 'paused'."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        inv = _make_invoice(session, debtor, date.today() + timedelta(days=5))
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/pause')
    assert resp.status_code == 200
    assert resp.json()['detail'] == 'Invoice paused'

    # Verify DB state
    session = SessionLocal()
    try:
        refreshed = session.query(Invoice).filter(Invoice.id == inv_id).first()
        assert refreshed.status == InvoiceStatus.paused
    finally:
        session.close()


def test_pause_overdue_invoice_400():
    """Pausing an overdue invoice returns 400."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Overdue Pause Corp")
        inv = _make_invoice(
            session, debtor,
            date.today() - timedelta(days=1),
            status=InvoiceStatus.overdue,
        )
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/pause')
    assert resp.status_code == 400


def test_pause_already_paused_invoice_400():
    """Pausing an already-paused invoice returns 400."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Already Paused Corp")
        inv = _make_invoice(
            session, debtor,
            date.today() + timedelta(days=3),
            status=InvoiceStatus.paused,
        )
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/pause')
    assert resp.status_code == 400
