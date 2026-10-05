"""Tests for C3: debtor.email and invoice.invoice_number must be unique
per-user, not globally. Two different customers can each have their own
debtor record for the same email, and both can use "INV-001" -- where
almost everyone's invoice numbering starts -- without colliding.
"""
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from src.app import app
from src.auth import get_current_user
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus
from src.models.user import User

client = TestClient(app)


def _make_active_user(session):
    u = User(
        id=str(uuid.uuid4()), username=f"{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="pwd", company_name="Tenant Test Co",
        subscription_status="active", subscription_plan="scale",
        chases_limit=750, chases_used=0,
    )
    session.add(u)
    session.flush()
    return u


def test_two_users_can_each_add_a_debtor_with_the_same_email():
    shared_email = f"shared-{uuid.uuid4().hex[:8]}@example.com"

    session = SessionLocal()
    try:
        user_a = _make_active_user(session)
        user_b = _make_active_user(session)
        session.commit()
        user_a_id, user_b_id = user_a.id, user_b.id
    finally:
        session.close()

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        session = SessionLocal()
        try:
            debtor_a = Debtor(id=str(uuid.uuid4()), user_id=user_a_id, name="Client A",
                               email=shared_email, debtor_type="business", voice_call_consent=False)
            session.add(debtor_a)
            session.commit()
        finally:
            session.close()

        # User B creates a debtor with the SAME email via the real API.
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_b_id, username="userb", company_name="B Co",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
        resp = client.post('/debtor', json={
            "name": "Client A (as seen by B)", "email": shared_email, "debtor_type": "business",
        })
        assert resp.status_code == 200, resp.text
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)


def test_two_users_can_each_use_invoice_number_inv_001():
    inv_number = f"INV-001-{uuid.uuid4().hex[:6]}"  # unique per test run, but identical across both users within it

    session = SessionLocal()
    try:
        user_a = _make_active_user(session)
        user_b = _make_active_user(session)
        debtor_a = Debtor(id=str(uuid.uuid4()), user_id=user_a.id, name="A Corp",
                           email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business")
        debtor_b = Debtor(id=str(uuid.uuid4()), user_id=user_b.id, name="B Corp",
                           email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business")
        session.add_all([debtor_a, debtor_b])
        session.flush()

        inv_a = Invoice(id=str(uuid.uuid4()), user_id=user_a.id, debtor_id=debtor_a.id,
                         invoice_number=inv_number, amount=100, due_date=date.today() + timedelta(days=5),
                         status=InvoiceStatus.upcoming)
        session.add(inv_a)
        session.commit()
        user_b_id, debtor_b_id = user_b.id, debtor_b.id
    finally:
        session.close()

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_b_id, username="userb", company_name="B Co",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
        resp = client.post('/invoice', json={
            "debtor_id": debtor_b_id, "invoice_number": inv_number,
            "amount": 250.0, "due_date": (date.today() + timedelta(days=10)).isoformat(),
        })
        assert resp.status_code == 200, resp.text
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)


def test_same_user_still_blocked_from_duplicate_invoice_number():
    """The per-tenant constraint must still enforce uniqueness WITHIN one
    account -- only the cross-tenant collision is lifted."""
    inv_number = f"INV-DUP-{uuid.uuid4().hex[:6]}"

    session = SessionLocal()
    try:
        user = _make_active_user(session)
        debtor = Debtor(id=str(uuid.uuid4()), user_id=user.id, name="Dup Corp",
                         email=f"{uuid.uuid4().hex[:8]}@example.com", debtor_type="business")
        session.add(debtor)
        session.flush()
        inv = Invoice(id=str(uuid.uuid4()), user_id=user.id, debtor_id=debtor.id,
                      invoice_number=inv_number, amount=100, due_date=date.today() + timedelta(days=5),
                      status=InvoiceStatus.upcoming)
        session.add(inv)
        session.commit()
        user_id, debtor_id = user.id, debtor.id
    finally:
        session.close()

    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=user_id, username="usera", company_name="A Co",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
        resp = client.post('/invoice', json={
            "debtor_id": debtor_id, "invoice_number": inv_number,
            "amount": 250.0, "due_date": (date.today() + timedelta(days=10)).isoformat(),
        })
        assert resp.status_code == 400
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)
