"""Tests for debtor CRUD — POST/GET/PUT/DELETE /debtor (M10)."""
import uuid

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.debtor import Debtor
from src.models.user import User
from src.auth import get_current_user

client = TestClient(app)


def _make_debtor(session, user_id="test-id", name="Debtor Test Co", email=None):
    d = Debtor(
        user_id=user_id,
        id=str(uuid.uuid4()),
        name=name,
        email=email or f"{uuid.uuid4().hex[:8]}@example.com",
        debtor_type="business",
    )
    session.add(d)
    session.flush()
    return d


def test_create_debtor_success():
    payload = {
        "name": "Acme Co",
        "email": f"{uuid.uuid4().hex[:8]}@example.com",
        "phone": "+15551234567",
        "debtor_type": "business",
        "voice_call_consent": True,
    }
    resp = client.post("/debtor", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Acme Co"
    assert data["email"] == payload["email"]
    assert data["voice_call_consent"] is True


def test_create_debtor_duplicate_email_for_same_user_rejected():
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    first = client.post("/debtor", json={"name": "First Co", "email": email})
    assert first.status_code == 200

    second = client.post("/debtor", json={"name": "Second Co", "email": email})
    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]


def test_create_debtor_same_email_allowed_across_different_users():
    """Uniqueness is scoped per-user — two different tenants may each have
    their own debtor record for the same email address."""
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
    finally:
        session.close()

    first = client.post("/debtor", json={"name": "Tenant A Co", "email": email})
    assert first.status_code == 200

    app.dependency_overrides[get_current_user] = lambda: User(
        id=other_user_id, username="other", subscription_status="active",
    )
    try:
        second = client.post("/debtor", json={"name": "Tenant B Co", "email": email})
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
    assert second.status_code == 200


def test_get_debtors_scoped_to_current_user():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        _make_debtor(session, user_id="test-id", name="Mine Co")
        _make_debtor(session, user_id=other_user_id, name="NotMine Co")
        session.commit()
    finally:
        session.close()

    resp = client.get("/debtor", params={"page_size": 200})
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()["items"]]
    assert "Mine Co" in names
    assert "NotMine Co" not in names


def test_get_debtors_search_by_name_or_email():
    session = SessionLocal()
    try:
        unique = uuid.uuid4().hex[:8]
        _make_debtor(session, name=f"SearchTarget-{unique}", email=f"searchtarget-{unique}@example.com")
        session.commit()
    finally:
        session.close()

    resp = client.get("/debtor", params={"search": unique, "page_size": 200})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert all(unique in d["name"] or unique in d["email"] for d in items)


def test_get_debtors_pagination_fields():
    resp = client.get("/debtor", params={"page": 1, "page_size": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert len(data["items"]) <= 1
    assert data["total_pages"] >= 1


def test_update_debtor_success():
    session = SessionLocal()
    try:
        d = _make_debtor(session, name="Before Update Co")
        session.commit()
        debtor_id = d.id
    finally:
        session.close()

    resp = client.put(f"/debtor/{debtor_id}", json={"name": "After Update Co", "voice_call_consent": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "After Update Co"
    assert data["voice_call_consent"] is True


def test_update_debtor_partial_fields_leave_others_untouched():
    session = SessionLocal()
    try:
        d = _make_debtor(session, name="Partial Co")
        d.phone = "+15550000000"
        session.commit()
        debtor_id = d.id
    finally:
        session.close()

    resp = client.put(f"/debtor/{debtor_id}", json={"voice_call_consent": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Partial Co"
    assert data["phone"] == "+15550000000"
    assert data["voice_call_consent"] is True


def test_update_debtor_not_found():
    resp = client.put(f"/debtor/{uuid.uuid4()}", json={"name": "Ghost Co"})
    assert resp.status_code == 404


def test_update_debtor_belonging_to_another_user_is_404():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        d = _make_debtor(session, user_id=other_user_id, name="Someone Elses Co")
        session.commit()
        debtor_id = d.id
    finally:
        session.close()

    resp = client.put(f"/debtor/{debtor_id}", json={"name": "Hijacked Co"})
    assert resp.status_code == 404


def test_delete_debtor_success():
    session = SessionLocal()
    try:
        d = _make_debtor(session, name="Delete Me Co")
        session.commit()
        debtor_id = d.id
    finally:
        session.close()

    resp = client.delete(f"/debtor/{debtor_id}")
    assert resp.status_code == 200

    session = SessionLocal()
    try:
        assert session.query(Debtor).filter(Debtor.id == debtor_id).first() is None
    finally:
        session.close()


def test_delete_debtor_not_found():
    resp = client.delete(f"/debtor/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_debtor_belonging_to_another_user_is_404():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other2_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        d = _make_debtor(session, user_id=other_user_id, name="Protected Co")
        session.commit()
        debtor_id = d.id
    finally:
        session.close()

    resp = client.delete(f"/debtor/{debtor_id}")
    assert resp.status_code == 404

    session = SessionLocal()
    try:
        assert session.query(Debtor).filter(Debtor.id == debtor_id).first() is not None
    finally:
        session.close()


def test_debtor_endpoints_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        assert client.get("/debtor").status_code == 401
        assert client.post("/debtor", json={"name": "X", "email": "x@example.com"}).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
