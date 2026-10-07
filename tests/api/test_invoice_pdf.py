"""Tests for GET /invoice/{id}/pdf (M10)."""
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.user import User
from src.auth import get_current_user

client = TestClient(app)


def test_download_invoice_pdf_success():
    debtor_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        debtor = Debtor(
            user_id='test-id', id=debtor_id, name="PDF Test Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business",
        )
        session.add(debtor)
        inv = Invoice(
            id=str(uuid.uuid4()), user_id='test-id', debtor_id=debtor_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=250.00,
            due_date=date.today() + timedelta(days=5), status=InvoiceStatus.upcoming,
        )
        session.add(inv)
        session.commit()
        inv_id = inv.id
        inv_number = inv.invoice_number
    finally:
        session.close()

    resp = client.get(f'/invoice/{inv_id}/pdf')
    assert resp.status_code == 200
    assert resp.headers['content-type'] == 'application/pdf'
    assert f'invoice_{inv_number}.pdf' in resp.headers['content-disposition']
    assert resp.content[:4] == b'%PDF'


def test_download_invoice_pdf_404_for_unknown_invoice():
    resp = client.get(f'/invoice/{uuid.uuid4()}/pdf')
    assert resp.status_code == 404


def test_download_invoice_pdf_404_for_another_users_invoice():
    other_user_id = str(uuid.uuid4())
    debtor_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        debtor = Debtor(
            user_id=other_user_id, id=debtor_id, name="Protected PDF Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business",
        )
        session.add(debtor)
        inv = Invoice(
            id=str(uuid.uuid4()), user_id=other_user_id, debtor_id=debtor_id,
            invoice_number=f"INV-{uuid.uuid4().hex[:6]}", amount=250.00,
            due_date=date.today() + timedelta(days=5), status=InvoiceStatus.upcoming,
        )
        session.add(inv)
        session.commit()
        inv_id = inv.id
    finally:
        session.close()

    resp = client.get(f'/invoice/{inv_id}/pdf')
    assert resp.status_code == 404


def test_download_invoice_pdf_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = client.get(f'/invoice/{uuid.uuid4()}/pdf')
        assert resp.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
