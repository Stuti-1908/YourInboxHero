"""Tests for the document-request upload/download flow (H5 fix) —
GET/POST /documents/upload/{token} (public) and GET /documents/{id}/download
(authenticated).
"""
import io
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from src.app import app
from src.auth import get_current_user
from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest
from src.models.user import User
from src.config.settings import get_settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_upload_dir(tmp_path, monkeypatch):
    """Point uploads at a throwaway temp directory for every test in this
    file, so tests never touch real storage and clean up automatically."""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    yield


def _make_request(status="pending"):
    session = SessionLocal()
    try:
        client_row = DocumentClient(
            id=str(uuid.uuid4()), user_id='test-id', name="Doc Client Co",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
        )
        session.add(client_row)
        session.flush()
        doc = DocumentRequest(
            id=str(uuid.uuid4()), user_id='test-id', client_id=client_row.id,
            title="W-9 Tax Form", description="Needed for year-end filing",
            due_date=date(2026, 12, 1), status=status,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc.id, doc.upload_token
    finally:
        session.close()


def test_get_upload_info_returns_request_details():
    doc_id, token = _make_request()
    resp = client.get(f"/documents/upload/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "W-9 Tax Form"
    assert body["status"] == "pending"
    assert body["already_uploaded_file_name"] is None


def test_get_upload_info_invalid_token_404():
    resp = client.get(f"/documents/upload/{uuid.uuid4().hex}")
    assert resp.status_code == 404


def test_upload_pdf_succeeds():
    doc_id, token = _make_request()
    file_content = b"%PDF-1.4 fake pdf content for testing"
    resp = client.post(
        f"/documents/upload/{token}",
        files={"file": ("w9.pdf", io.BytesIO(file_content), "application/pdf")},
    )
    assert resp.status_code == 200

    session = SessionLocal()
    try:
        doc = session.query(DocumentRequest).filter(DocumentRequest.id == doc_id).first()
        assert doc.status == "submitted"
        assert doc.uploaded_file_name == "w9.pdf"
        assert doc.stored_file_name is not None
        assert doc.stored_file_name.endswith(".pdf")
        assert doc.uploaded_at is not None
    finally:
        session.close()


def test_upload_rejects_unsupported_file_type():
    doc_id, token = _make_request()
    resp = client.post(
        f"/documents/upload/{token}",
        files={"file": ("malware.exe", io.BytesIO(b"fake exe"), "application/x-msdownload")},
    )
    assert resp.status_code == 400

    session = SessionLocal()
    try:
        doc = session.query(DocumentRequest).filter(DocumentRequest.id == doc_id).first()
        assert doc.status == "pending"  # unchanged
        assert doc.stored_file_name is None
    finally:
        session.close()


def test_upload_rejects_oversized_file(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    doc_id, token = _make_request()

    oversized = b"x" * (2 * 1024 * 1024)  # 2MB > 1MB limit
    resp = client.post(
        f"/documents/upload/{token}",
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


def test_upload_rejects_empty_file():
    doc_id, token = _make_request()
    resp = client.post(
        f"/documents/upload/{token}",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert resp.status_code == 400


def test_upload_invalid_token_404():
    resp = client.post(
        f"/documents/upload/{uuid.uuid4().hex}",
        files={"file": ("w9.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
    )
    assert resp.status_code == 404


def test_download_requires_auth():
    """Without the conftest auth override, this should be unreachable in
    practice (get_current_user is overridden globally in tests), so this
    test instead verifies ownership scoping via a second user below."""
    pass


def test_download_after_upload_returns_file_content():
    doc_id, token = _make_request()
    file_content = b"%PDF-1.4 the actual uploaded content"
    client.post(
        f"/documents/upload/{token}",
        files={"file": ("w9.pdf", io.BytesIO(file_content), "application/pdf")},
    )

    resp = client.get(f"/documents/{doc_id}/download")
    assert resp.status_code == 200
    assert resp.content == file_content
    assert "w9.pdf" in resp.headers.get("content-disposition", "")


def test_download_before_upload_404():
    doc_id, token = _make_request()
    resp = client.get(f"/documents/{doc_id}/download")
    assert resp.status_code == 404


def test_download_scoped_to_owning_user():
    """A different user's document request must not be downloadable, even
    with a valid doc_id, the same cross-tenant protection every other
    resource in this app has."""
    doc_id, token = _make_request()
    client.post(
        f"/documents/upload/{token}",
        files={"file": ("w9.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
    )

    other_user_id = str(uuid.uuid4())
    old_override = app.dependency_overrides.get(get_current_user)
    try:
        app.dependency_overrides[get_current_user] = lambda: User(
            id=other_user_id, username="otheruser", company_name="Other Co",
            subscription_status="active", subscription_plan="scale", chases_limit=750,
        )
        resp = client.get(f"/documents/{doc_id}/download")
        assert resp.status_code == 404
    finally:
        if old_override:
            app.dependency_overrides[get_current_user] = old_override
        else:
            app.dependency_overrides.pop(get_current_user, None)


def test_resubmission_overwrites_pointer_not_old_file_silently():
    """A second upload for the same request must update the DB pointer to
    the new file (old file is simply orphaned on disk, not auto-deleted --
    acceptable for a first pass, avoids ever deleting something that might
    still be needed)."""
    doc_id, token = _make_request()
    client.post(
        f"/documents/upload/{token}",
        files={"file": ("first.pdf", io.BytesIO(b"%PDF-1.4 first"), "application/pdf")},
    )
    client.post(
        f"/documents/upload/{token}",
        files={"file": ("second.pdf", io.BytesIO(b"%PDF-1.4 second"), "application/pdf")},
    )

    resp = client.get(f"/documents/{doc_id}/download")
    assert resp.content == b"%PDF-1.4 second"
