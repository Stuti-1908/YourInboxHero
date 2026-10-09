"""Tests for document client CRUD — POST/GET /document-clients (M10)."""
import uuid

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.user import User
from src.auth import get_current_user

client = TestClient(app)


def test_create_document_client_success():
    payload = {"name": "Acme Docs Co", "email": f"{uuid.uuid4().hex[:8]}@example.com", "phone": "+15551234567"}
    resp = client.post("/document-clients", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Acme Docs Co"
    assert data["email"] == payload["email"]
    assert data["phone"] == "+15551234567"
    assert data["voice_call_consent"] is False  # default, must opt in explicitly
    assert "id" in data


def test_create_document_client_with_voice_consent():
    payload = {
        "name": "Consented Co", "email": f"{uuid.uuid4().hex[:8]}@example.com",
        "phone": "+15551234567", "voice_call_consent": True,
    }
    resp = client.post("/document-clients", json=payload)
    assert resp.status_code == 200
    assert resp.json()["voice_call_consent"] is True


def test_update_document_client_voice_consent():
    """Mirrors PUT /debtor/{id} -- consent is usually granted after the
    client was first added (e.g. once a signed consent form comes back)."""
    session = SessionLocal()
    try:
        c = DocumentClient(
            user_id="test-id", id=str(uuid.uuid4()), name="Update Consent Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com", voice_call_consent=False,
        )
        session.add(c)
        session.commit()
        client_id = c.id
    finally:
        session.close()

    resp = client.put(f"/document-clients/{client_id}", json={"voice_call_consent": True})
    assert resp.status_code == 200
    assert resp.json()["voice_call_consent"] is True


def test_update_document_client_not_found():
    resp = client.put(f"/document-clients/{uuid.uuid4()}", json={"voice_call_consent": True})
    assert resp.status_code == 404


def test_update_document_client_belonging_to_another_user_is_404():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other2_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        c = DocumentClient(
            user_id=other_user_id, id=str(uuid.uuid4()), name="Protected Doc Client Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
        )
        session.add(c)
        session.commit()
        client_id = c.id
    finally:
        session.close()

    resp = client.put(f"/document-clients/{client_id}", json={"voice_call_consent": True})
    assert resp.status_code == 404


def test_create_document_client_without_phone():
    payload = {"name": "No Phone Co", "email": f"{uuid.uuid4().hex[:8]}@example.com"}
    resp = client.post("/document-clients", json=payload)
    assert resp.status_code == 200
    assert resp.json()["phone"] is None


def test_get_document_clients_scoped_to_current_user():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        session.add(DocumentClient(
            user_id="test-id", id=str(uuid.uuid4()), name="Mine Doc Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
        ))
        session.add(DocumentClient(
            user_id=other_user_id, id=str(uuid.uuid4()), name="NotMine Doc Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
        ))
        session.commit()
    finally:
        session.close()

    resp = client.get("/document-clients")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Mine Doc Co" in names
    assert "NotMine Doc Co" not in names


def test_create_document_client_requires_active_subscription():
    app.dependency_overrides[get_current_user] = lambda: User(
        id="test-id", username="testuser", subscription_status="past_due",
    )
    try:
        resp = client.post("/document-clients", json={"name": "X", "email": "x@example.com"})
        assert resp.status_code == 402
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )


def test_document_client_endpoints_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        assert client.get("/document-clients").status_code == 401
        assert client.post("/document-clients", json={"name": "X", "email": "x@example.com"}).status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
