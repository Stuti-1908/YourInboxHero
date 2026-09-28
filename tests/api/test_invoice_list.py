"""Tests for the GET /invoice endpoint."""
import uuid
from datetime import date, timedelta
from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus

client = TestClient(app)

def _make_debtor(session, name="List Corp"):
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

def test_list_invoices_returns_200():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        inv = _make_invoice(session, debtor, date.today() + timedelta(days=5))
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.get('/invoice')
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert any(i['id'] == inv_id for i in data["items"])