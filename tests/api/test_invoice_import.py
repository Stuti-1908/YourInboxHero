"""Tests for CSV bulk import — POST /invoice/import/preview and /commit."""
import io
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice

client = TestClient(app)


def _csv_file(content: str, filename="import.csv"):
    return {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}


def test_preview_missing_required_columns():
    csv_content = "name,email\nAcme Co,ap@acme.com\n"
    resp = client.post("/invoice/import/preview", files=_csv_file(csv_content))
    assert resp.status_code == 400
    assert "missing required column" in resp.json()["detail"].lower()


def test_preview_valid_rows():
    tomorrow = (date.today() + timedelta(days=30)).isoformat()
    csv_content = (
        "debtor_name,debtor_email,debtor_phone,invoice_number,amount,due_date,description\n"
        f"Acme Imports,{uuid.uuid4().hex[:8]}@example.com,+15551234567,INV-IMP-{uuid.uuid4().hex[:6]},1200.50,{tomorrow},Consulting\n"
    )
    resp = client.post("/invoice/import/preview", files=_csv_file(csv_content))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["valid_rows"]) == 1
    assert len(body["errors"]) == 0
    assert body["valid_rows"][0]["amount"] == 1200.50
    assert body["valid_rows"][0]["debtor_exists"] is False


def test_preview_flags_row_errors_without_failing_whole_request():
    good_email = f"{uuid.uuid4().hex[:8]}@example.com"
    tomorrow = (date.today() + timedelta(days=10)).isoformat()
    csv_content = (
        "debtor_name,debtor_email,invoice_number,amount,due_date\n"
        f"Good Co,{good_email},INV-GOOD-{uuid.uuid4().hex[:6]},500,{tomorrow}\n"
        "Bad Amount Co,bad@example.com,INV-BAD-1,not-a-number,2026-01-01\n"
        "Bad Date Co,bad2@example.com,INV-BAD-2,500,not-a-date\n"
        "Missing Email Co,,INV-BAD-3,500,2026-01-01\n"
    )
    resp = client.post("/invoice/import/preview", files=_csv_file(csv_content))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["valid_rows"]) == 1
    assert len(body["errors"]) == 3


def test_preview_flags_duplicate_invoice_number_within_file():
    tomorrow = (date.today() + timedelta(days=10)).isoformat()
    dupe_number = f"INV-DUPE-{uuid.uuid4().hex[:6]}"
    csv_content = (
        "debtor_name,debtor_email,invoice_number,amount,due_date\n"
        f"Co A,{uuid.uuid4().hex[:8]}@example.com,{dupe_number},500,{tomorrow}\n"
        f"Co B,{uuid.uuid4().hex[:8]}@example.com,{dupe_number},600,{tomorrow}\n"
    )
    resp = client.post("/invoice/import/preview", files=_csv_file(csv_content))
    body = resp.json()
    assert len(body["valid_rows"]) == 1
    assert len(body["errors"]) == 1
    assert "duplicate" in body["errors"][0]["error"].lower()


def test_preview_flags_existing_invoice_number():
    session = SessionLocal()
    try:
        d = Debtor(user_id='test-id', id=str(uuid.uuid4()), name="Existing Corp",
                   email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business")
        session.add(d)
        session.flush()
        existing_number = f"INV-EXIST-{uuid.uuid4().hex[:6]}"
        inv = Invoice(id=str(uuid.uuid4()), user_id='test-id', debtor_id=d.id, invoice_number=existing_number,
                      amount=100, due_date=date.today() + timedelta(days=5),
                      status="upcoming")
        session.add(inv)
        session.commit()
    finally:
        session.close()

    csv_content = (
        "debtor_name,debtor_email,invoice_number,amount,due_date\n"
        f"Dup Co,{uuid.uuid4().hex[:8]}@example.com,{existing_number},500,{(date.today() + timedelta(days=10)).isoformat()}\n"
    )
    resp = client.post("/invoice/import/preview", files=_csv_file(csv_content))
    body = resp.json()
    assert len(body["valid_rows"]) == 0
    assert "already exists" in body["errors"][0]["error"]


def test_commit_creates_debtor_and_invoice():
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    invoice_number = f"INV-COMMIT-{uuid.uuid4().hex[:6]}"
    payload = {
        "rows": [{
            "row_number": 2,
            "debtor_name": "New Commit Co",
            "debtor_email": email,
            "debtor_phone": None,
            "invoice_number": invoice_number,
            "amount": 999.99,
            "due_date": (date.today() + timedelta(days=15)).isoformat(),
            "description": None,
            "debtor_exists": False,
        }]
    }
    resp = client.post("/invoice/import/commit", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 1
    assert body["results"][0]["status"] == "created"

    session = SessionLocal()
    try:
        debtor = session.query(Debtor).filter(Debtor.email == email).first()
        assert debtor is not None
        assert debtor.user_id == "test-id"
        inv = session.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
        assert inv is not None
        assert float(inv.amount) == 999.99
    finally:
        session.close()


def test_commit_reuses_existing_debtor_for_second_invoice():
    """Two rows for the same debtor_email in one commit must create one
    debtor, not fail on the second row's unique-email constraint."""
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    inv1 = f"INV-REUSE-A-{uuid.uuid4().hex[:6]}"
    inv2 = f"INV-REUSE-B-{uuid.uuid4().hex[:6]}"
    payload = {
        "rows": [
            {
                "row_number": 2, "debtor_name": "Reuse Co", "debtor_email": email,
                "debtor_phone": None, "invoice_number": inv1, "amount": 100,
                "due_date": (date.today() + timedelta(days=5)).isoformat(),
                "description": None, "debtor_exists": False,
            },
            {
                "row_number": 3, "debtor_name": "Reuse Co", "debtor_email": email,
                "debtor_phone": None, "invoice_number": inv2, "amount": 200,
                "due_date": (date.today() + timedelta(days=6)).isoformat(),
                "description": None, "debtor_exists": False,
            },
        ]
    }
    resp = client.post("/invoice/import/commit", json=payload)
    body = resp.json()
    assert body["created_count"] == 2

    session = SessionLocal()
    try:
        debtors = session.query(Debtor).filter(Debtor.email == email).all()
        assert len(debtors) == 1
    finally:
        session.close()


def test_commit_skips_row_with_duplicate_invoice_number_but_continues():
    """One bad row in a batch must not abort the rest of the commit."""
    session = SessionLocal()
    try:
        d = Debtor(user_id='test-id', id=str(uuid.uuid4()), name="Pre-existing Corp",
                   email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business")
        session.add(d)
        session.flush()
        existing_number = f"INV-SKIP-{uuid.uuid4().hex[:6]}"
        inv = Invoice(id=str(uuid.uuid4()), user_id='test-id', debtor_id=d.id, invoice_number=existing_number,
                      amount=50, due_date=date.today() + timedelta(days=5), status="upcoming")
        session.add(inv)
        session.commit()
    finally:
        session.close()

    good_number = f"INV-GOOD-COMMIT-{uuid.uuid4().hex[:6]}"
    payload = {
        "rows": [
            {
                "row_number": 2, "debtor_name": "Dup Row Co", "debtor_email": f"{uuid.uuid4().hex[:8]}@example.com",
                "debtor_phone": None, "invoice_number": existing_number, "amount": 100,
                "due_date": (date.today() + timedelta(days=5)).isoformat(),
                "description": None, "debtor_exists": False,
            },
            {
                "row_number": 3, "debtor_name": "Good Row Co", "debtor_email": f"{uuid.uuid4().hex[:8]}@example.com",
                "debtor_phone": None, "invoice_number": good_number, "amount": 150,
                "due_date": (date.today() + timedelta(days=5)).isoformat(),
                "description": None, "debtor_exists": False,
            },
        ]
    }
    resp = client.post("/invoice/import/commit", json=payload)
    body = resp.json()
    assert body["skipped_count"] == 1
    assert body["created_count"] == 1

    session = SessionLocal()
    try:
        assert session.query(Invoice).filter(Invoice.invoice_number == good_number).first() is not None
    finally:
        session.close()
