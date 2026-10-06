"""Tests for GET /analytics — aging buckets, status breakdown, monthly
recovered totals, recovery rate, and per-tenant isolation (M10)."""
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


def _make_debtor(session, user_id="test-id", name="Analytics Corp"):
    d = Debtor(
        user_id=user_id,
        id=str(uuid.uuid4()),
        name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def _make_invoice(session, debtor, due_date, amount, status):
    inv = Invoice(
        id=str(uuid.uuid4()),
        user_id=debtor.user_id,
        debtor_id=debtor.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        amount=amount,
        due_date=due_date,
        status=status,
    )
    session.add(inv)
    session.flush()
    return inv


def test_analytics_empty_state_has_no_division_by_zero():
    """A brand-new account with zero invoices must not 500 on the recovery
    rate's division — it should return clean zeroed-out data."""
    session = SessionLocal()
    try:
        # Use a fresh, invoice-less debtor's user so no other test's data
        # leaks in via the shared 'test-id' user.
        fresh_user_id = str(uuid.uuid4())
        session.add(User(id=fresh_user_id, username=f"empty_{fresh_user_id[:8]}", hashed_password="x"))
        session.commit()
    finally:
        session.close()

    app.dependency_overrides[get_current_user] = lambda: User(id=fresh_user_id, username="empty")
    try:
        resp = client.get("/analytics")
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_outstanding"] == 0.0
    assert data["total_recovered"] == 0.0
    assert data["recovery_rate"] == 0.0
    assert data["aging"] == {"current": 0.0, "days_30": 0.0, "days_60": 0.0, "days_90_plus": 0.0}
    assert data["status_breakdown"] == {}
    assert data["monthly_recovered"] == []


def test_analytics_outstanding_vs_recovered_split_and_recovery_rate():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session)
        _make_invoice(session, debtor, date.today() + timedelta(days=10), 100.0, InvoiceStatus.upcoming)
        _make_invoice(session, debtor, date.today() - timedelta(days=5), 300.0, InvoiceStatus.paid)
        session.commit()
    finally:
        session.close()

    resp = client.get("/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_outstanding"] >= 100.0
    assert data["total_recovered"] >= 300.0
    # recovery_rate = recovered / (outstanding + recovered) * 100
    expected_rate = round(data["total_recovered"] / (data["total_outstanding"] + data["total_recovered"]) * 100, 2)
    assert data["recovery_rate"] == expected_rate


def test_analytics_aging_buckets_split_by_days_overdue():
    """Unpaid invoices bucket into current/<30/<60/<90/90+ days overdue
    based on due_date, independent of their actual InvoiceStatus value."""
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Aging Corp")
        current_inv = _make_invoice(session, debtor, date.today() - timedelta(days=5), 10.0, InvoiceStatus.due)
        d30_inv = _make_invoice(session, debtor, date.today() - timedelta(days=35), 20.0, InvoiceStatus.overdue)
        d60_inv = _make_invoice(session, debtor, date.today() - timedelta(days=65), 30.0, InvoiceStatus.overdue)
        d90_inv = _make_invoice(session, debtor, date.today() - timedelta(days=95), 40.0, InvoiceStatus.overdue)
        session.commit()
        ids = [current_inv.id, d30_inv.id, d60_inv.id, d90_inv.id]
    finally:
        session.close()

    resp = client.get("/analytics")
    assert resp.status_code == 200
    aging = resp.json()["aging"]
    # These are cumulative across all of test-id's invoices (shared fixture
    # user across this file), so assert each bucket is at least the amount
    # this test itself contributed rather than an exact total.
    assert aging["current"] >= 10.0
    assert aging["days_30"] >= 20.0
    assert aging["days_60"] >= 30.0
    assert aging["days_90_plus"] >= 40.0

    # Clean up so later tests in this file aren't skewed by these amounts.
    session = SessionLocal()
    try:
        session.query(Invoice).filter(Invoice.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def test_analytics_status_breakdown_counts_each_status():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Status Corp")
        _make_invoice(session, debtor, date.today() + timedelta(days=1), 5.0, InvoiceStatus.upcoming)
        _make_invoice(session, debtor, date.today() + timedelta(days=1), 5.0, InvoiceStatus.upcoming)
        _make_invoice(session, debtor, date.today() - timedelta(days=1), 5.0, InvoiceStatus.paid)
        session.commit()
    finally:
        session.close()

    resp = client.get("/analytics")
    assert resp.status_code == 200
    breakdown = resp.json()["status_breakdown"]
    assert breakdown.get("upcoming", 0) >= 2
    assert breakdown.get("paid", 0) >= 1


def test_analytics_monthly_recovered_groups_paid_invoices_by_due_month():
    session = SessionLocal()
    try:
        debtor = _make_debtor(session, name="Monthly Corp")
        due_date = date(2026, 3, 15)
        _make_invoice(session, debtor, due_date, 123.45, InvoiceStatus.paid)
        session.commit()
    finally:
        session.close()

    resp = client.get("/analytics")
    assert resp.status_code == 200
    monthly = resp.json()["monthly_recovered"]
    march_entry = next((m for m in monthly if m["month"] == "2026-03"), None)
    assert march_entry is not None
    assert march_entry["amount"] >= 123.45


def test_analytics_scoped_to_current_user_only():
    """An invoice belonging to a different user's debtor must never appear
    in another user's analytics totals — this is the multi-tenancy
    boundary the endpoint's join+filter is responsible for."""
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        other_debtor = _make_debtor(session, user_id=other_user_id, name="Other Tenant Corp")
        _make_invoice(session, other_debtor, date.today(), 999999.0, InvoiceStatus.paid)
        session.commit()
    finally:
        session.close()

    resp = client.get("/analytics")
    assert resp.status_code == 200
    # test-id's totals must not include the other tenant's huge invoice.
    assert resp.json()["total_recovered"] < 999999.0


def test_analytics_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        resp = client.get("/analytics")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
