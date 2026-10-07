"""Tests for document request CRUD — GET/POST/DELETE /documents (M10).

The public upload/download/info flow is already covered by
test_document_upload.py; this file covers the authenticated
list/create/delete endpoints in document_request.py.
"""
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from src.app import app
from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest
from src.models.user import User
from src.auth import get_current_user

client = TestClient(app)


def _make_client(session, user_id="test-id", name="Doc Req Test Co"):
    c = DocumentClient(
        user_id=user_id, id=str(uuid.uuid4()), name=name,
        email=f"{uuid.uuid4().hex[:8]}@example.com",
    )
    session.add(c)
    session.flush()
    return c


def test_create_document_request_success():
    session = SessionLocal()
    try:
        doc_client = _make_client(session)
        session.commit()
        client_id = doc_client.id
    finally:
        session.close()

    payload = {
        "client_id": client_id,
        "title": "W-9 Form",
        "description": "Please upload a signed W-9",
        "due_date": str(date.today() + timedelta(days=7)),
    }
    resp = client.post("/documents", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "W-9 Form"
    assert data["status"] == "pending"
    assert data["client"]["id"] == client_id
    assert "upload_token" in data


def test_create_document_request_404_for_unknown_client():
    payload = {
        "client_id": str(uuid.uuid4()),
        "title": "Ghost Form",
        "due_date": str(date.today() + timedelta(days=7)),
    }
    resp = client.post("/documents", json=payload)
    assert resp.status_code == 404


def test_create_document_request_404_for_another_users_client():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        doc_client = _make_client(session, user_id=other_user_id, name="Other Tenant Doc Co")
        session.commit()
        client_id = doc_client.id
    finally:
        session.close()

    payload = {"client_id": client_id, "title": "Stolen Form", "due_date": str(date.today() + timedelta(days=7))}
    resp = client.post("/documents", json=payload)
    assert resp.status_code == 404


def test_list_document_requests_scoped_to_current_user():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other2_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        my_client = _make_client(session, name="Listable Mine Co")
        other_client = _make_client(session, user_id=other_user_id, name="Listable NotMine Co")
        session.add(DocumentRequest(
            user_id="test-id", id=str(uuid.uuid4()), client_id=my_client.id,
            title="Mine Request", due_date=date.today() + timedelta(days=5), status="pending",
        ))
        session.add(DocumentRequest(
            user_id=other_user_id, id=str(uuid.uuid4()), client_id=other_client.id,
            title="NotMine Request", due_date=date.today() + timedelta(days=5), status="pending",
        ))
        session.commit()
    finally:
        session.close()

    resp = client.get("/documents")
    assert resp.status_code == 200
    titles = [d["title"] for d in resp.json()]
    assert "Mine Request" in titles
    assert "NotMine Request" not in titles


def test_delete_document_request_success():
    session = SessionLocal()
    try:
        doc_client = _make_client(session, name="Delete Me Doc Co")
        doc = DocumentRequest(
            user_id="test-id", id=str(uuid.uuid4()), client_id=doc_client.id,
            title="Delete Me Request", due_date=date.today() + timedelta(days=5), status="pending",
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id
    finally:
        session.close()

    resp = client.delete(f"/documents/{doc_id}")
    assert resp.status_code == 200

    session = SessionLocal()
    try:
        assert session.query(DocumentRequest).filter(DocumentRequest.id == doc_id).first() is None
    finally:
        session.close()


def test_delete_document_request_not_found():
    resp = client.delete(f"/documents/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_document_request_belonging_to_another_user_is_404():
    other_user_id = str(uuid.uuid4())
    session = SessionLocal()
    try:
        session.add(User(id=other_user_id, username=f"other3_{other_user_id[:8]}", hashed_password="x"))
        session.commit()
        doc_client = _make_client(session, user_id=other_user_id, name="Protected Doc Co")
        doc = DocumentRequest(
            user_id=other_user_id, id=str(uuid.uuid4()), client_id=doc_client.id,
            title="Protected Request", due_date=date.today() + timedelta(days=5), status="pending",
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id
    finally:
        session.close()

    resp = client.delete(f"/documents/{doc_id}")
    assert resp.status_code == 404

    session = SessionLocal()
    try:
        assert session.query(DocumentRequest).filter(DocumentRequest.id == doc_id).first() is not None
    finally:
        session.close()


def test_document_request_endpoints_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        assert client.get("/documents").status_code == 401
        assert client.delete(f"/documents/{uuid.uuid4()}").status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = lambda: User(
            id="test-id", username="testuser", company_name="Test Corp",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
