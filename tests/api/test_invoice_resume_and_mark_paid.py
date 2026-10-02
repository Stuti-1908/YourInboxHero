"""Tests for POST /invoice/{id}/resume and POST /invoice/{id}/mark-paid.

mark-paid is the fix for a real gap: there was previously no way to stop
automated reminders once a debtor actually paid, short of deleting them
entirely (losing their history). Every sweep query filters on status, so
once status == paid, src/scheduler.py's overdue-only queries naturally
stop matching it -- these tests just confirm the status transition itself.
"""
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus

client = TestClient(app)


def _make_debtor(session, name="MarkPaid Corp"):
    d = Debtor(
        user_id='test-id',
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


# ---------- mark-paid ----------

def test_mark_paid_404():
    resp = client.post(f'/invoice/{uuid.uuid4()}/mark-paid')
    assert resp.status_code == 404


def test_mark_overdue_invoice_paid_200():
    """The real-world case: a debtor pays an overdue invoice, must stop chasing them."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Overdue MarkPaid Corp")
        inv = _make_invoice(session, debtor, date.today() - timedelta(days=10), status=InvoiceStatus.overdue)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/mark-paid')
    assert resp.status_code == 200
    assert resp.json()['detail'] == 'Invoice marked as paid'

    session = SessionLocal()
    try:
        refreshed = session.query(Invoice).filter(Invoice.id == inv_id).first()
        assert refreshed.status == InvoiceStatus.paid
    finally:
        session.close()


def test_mark_upcoming_invoice_paid_200():
    """Paying early/on-time should also be markable, not just overdue invoices."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Early MarkPaid Corp")
        inv = _make_invoice(session, debtor, date.today() + timedelta(days=5))
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/mark-paid')
    assert resp.status_code == 200


def test_mark_already_paid_invoice_400():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Already Paid Corp")
        inv = _make_invoice(session, debtor, date.today() - timedelta(days=1), status=InvoiceStatus.paid)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/mark-paid')
    assert resp.status_code == 400


# ---------- resume ----------

def test_resume_404():
    resp = client.post(f'/invoice/{uuid.uuid4()}/resume')
    assert resp.status_code == 404


def test_resume_non_paused_invoice_400():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Not Paused Corp")
        inv = _make_invoice(session, debtor, date.today() + timedelta(days=5), status=InvoiceStatus.upcoming)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/resume')
    assert resp.status_code == 400


def test_resume_paused_future_invoice_becomes_upcoming():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Resume Future Corp")
        inv = _make_invoice(session, debtor, date.today() + timedelta(days=10), status=InvoiceStatus.paused)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/resume')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'upcoming'


def test_resume_paused_overdue_invoice_becomes_overdue_not_upcoming():
    """A paused invoice whose due date has already passed must resume as
    'overdue', not silently reset to 'upcoming' -- otherwise resuming would
    itself reset the escalation clock and skip a day of overdue status."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Resume Past Corp")
        inv = _make_invoice(session, debtor, date.today() - timedelta(days=3), status=InvoiceStatus.paused)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.post(f'/invoice/{inv_id}/resume')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'overdue'
