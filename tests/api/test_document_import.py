"""Tests for the combined document-request flow: POST /documents/batch
(existing or inline client + several titles, one email) and the CSV/.xlsx
import preview/commit endpoints."""
import io
import uuid
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.app import app
from src.db import SessionLocal
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest

client = TestClient(app)
SEND = 'src.services.document_email.send_document_request_email'


def _future(days=7):
    return str(date.today() + timedelta(days=days))


def _email():
    return f"{uuid.uuid4().hex[:8]}@example.com"


def _make_client(email=None, name="Batch Co"):
    session = SessionLocal()
    try:
        c = DocumentClient(user_id="test-id", id=str(uuid.uuid4()), name=name, email=email or _email())
        session.add(c)
        session.commit()
        return c.id, c.email
    finally:
        session.close()


def _requests_for(client_id):
    session = SessionLocal()
    try:
        return session.query(DocumentRequest).filter(DocumentRequest.client_id == client_id).all()
    finally:
        session.close()


# ---- /documents/batch ------------------------------------------------------

def test_batch_new_client_creates_all_titles_and_sends_one_email():
    email = _email()
    with patch(SEND) as mock_send:
        resp = client.post("/documents/batch", json={
            "client": {"name": "New Person", "email": email.upper()},
            "titles": ["W-9", "Bank statement", "  ", "w-9"],
            "due_date": _future(),
        })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["client_email"] == email  # normalised to lower case
    assert [r["title"] for r in data["requests"]] == ["W-9", "Bank statement"]  # blank + case-dup dropped
    assert data["email_sent"] is True
    mock_send.assert_called_once()
    assert len(mock_send.call_args.args[0]) == 2  # both docs in ONE email


def test_batch_reuses_existing_client_by_email_instead_of_duplicating():
    client_id, email = _make_client()
    with patch(SEND):
        resp = client.post("/documents/batch", json={
            "client": {"name": "Different Name", "email": email.upper(), "phone": "+15550001111"},
            "titles": ["Passport"],
            "due_date": _future(),
        })
    assert resp.status_code == 200, resp.text
    assert resp.json()["client_id"] == client_id
    session = SessionLocal()
    try:
        assert session.query(DocumentClient).filter(DocumentClient.user_id == "test-id").filter(
            DocumentClient.email.in_([email, email.upper()])).count() == 1
        reused = session.query(DocumentClient).get(client_id)
        assert reused.name == "Batch Co"  # existing data never overwritten
        assert reused.phone == "+15550001111"  # gap filled
    finally:
        session.close()


def test_batch_with_existing_client_id():
    client_id, _ = _make_client()
    with patch(SEND):
        resp = client.post("/documents/batch", json={
            "client_id": client_id, "titles": ["Lease"], "due_date": _future(),
        })
    assert resp.status_code == 200
    assert len(_requests_for(client_id)) == 1


def test_batch_rejects_duplicate_of_open_request():
    client_id, _ = _make_client()
    with patch(SEND):
        assert client.post("/documents/batch", json={"client_id": client_id, "titles": ["ID"], "due_date": _future()}).status_code == 200
        resp = client.post("/documents/batch", json={"client_id": client_id, "titles": ["id"], "due_date": _future()})
    assert resp.status_code == 409
    assert len(_requests_for(client_id)) == 1


def test_batch_validation_errors():
    client_id, _ = _make_client()
    cases = [
        ({"titles": ["A"], "due_date": _future()}, 422),  # no client at all
        ({"client_id": client_id, "client": {"name": "x", "email": _email()}, "titles": ["A"], "due_date": _future()}, 422),
        ({"client_id": client_id, "titles": ["  "], "due_date": _future()}, 422),
        ({"client_id": client_id, "titles": ["A"], "due_date": str(date.today() - timedelta(days=1))}, 422),
        ({"client_id": client_id, "titles": [f"T{i}" for i in range(21)], "due_date": _future()}, 422),
        ({"client": {"name": "x", "email": "not-an-email"}, "titles": ["A"], "due_date": _future()}, 422),
        ({"client": {"name": "x", "email": _email(), "voice_call_consent": True}, "titles": ["A"], "due_date": _future()}, 422),
        ({"client_id": "does-not-exist", "titles": ["A"], "due_date": _future()}, 404),
    ]
    with patch(SEND) as mock_send:
        for body, expected in cases:
            assert client.post("/documents/batch", json=body).status_code == expected, body
    mock_send.assert_not_called()


def test_batch_still_creates_requests_when_email_fails():
    client_id, _ = _make_client()
    with patch(SEND, side_effect=Exception("Resend down")):
        resp = client.post("/documents/batch", json={"client_id": client_id, "titles": ["A", "B"], "due_date": _future()})
    assert resp.status_code == 200
    assert resp.json()["email_sent"] is False
    assert len(_requests_for(client_id)) == 2


# ---- /documents/import -----------------------------------------------------

def _csv(rows, header="client_name,client_email,document_title,due_date,client_phone"):
    return ("\n".join([header] + rows)).encode("utf-8")


def test_import_preview_flags_errors_and_writes_nothing():
    e = _email()
    raw = _csv([
        f"Ann,{e},W-9,{_future()},",
        f"Ann,{e},w-9,{_future()},",              # duplicate in file
        f"Bob,bad-email,ID,{_future()},",
        f"Cat,{_email()},ID,2001-01-01,",           # past
        f"Dan,{_email()},ID,31/12/2030,",           # bad format
        f",{_email()},ID,{_future()},",             # missing name
    ])
    resp = client.post("/documents/import/preview", files={"file": ("docs.csv", raw, "text/csv")})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert [r["row_number"] for r in data["valid_rows"]] == [2]
    assert [e["row_number"] for e in data["errors"]] == [3, 4, 5, 6, 7]
    assert data["total_rows"] == 6
    session = SessionLocal()
    try:
        assert session.query(DocumentClient).filter(DocumentClient.email == e).count() == 0
    finally:
        session.close()


def test_import_preview_missing_column_is_400():
    resp = client.post("/documents/import/preview",
                       files={"file": ("docs.csv", b"client_name,client_email\nA,a@b.co", "text/csv")})
    assert resp.status_code == 400
    assert "document_title" in resp.json()["detail"]


def test_import_preview_accepts_xlsx_with_real_dates():
    wb = Workbook()
    ws = wb.active
    ws.append(["Client_Name", "Client_Email", "Document_Title", "Due_Date"])
    ws.append(["Xena", _email(), "Contract", date.today() + timedelta(days=3)])
    buf = io.BytesIO()
    wb.save(buf)
    resp = client.post("/documents/import/preview", files={"file": ("docs.xlsx", buf.getvalue(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["valid_rows"]
    assert len(rows) == 1 and rows[0]["due_date"] == _future(3)


def test_import_commit_groups_one_email_per_client_and_skips_open_duplicates():
    existing_id, existing_email = _make_client(name="Existing")
    with patch(SEND):
        client.post("/documents/batch", json={"client_id": existing_id, "titles": ["Payslip"], "due_date": _future()})

    new_email = _email()
    rows = [
        {"row_number": 2, "client_name": "New", "client_email": new_email, "document_title": "A", "due_date": _future()},
        {"row_number": 3, "client_name": "New", "client_email": new_email, "document_title": "B", "due_date": _future(9)},
        {"row_number": 4, "client_name": "Existing", "client_email": existing_email, "document_title": "Payslip", "due_date": _future()},
        {"row_number": 5, "client_name": "Existing", "client_email": existing_email, "document_title": "Tax return", "due_date": _future()},
        {"row_number": 6, "client_name": "Old", "client_email": _email(), "document_title": "Z", "due_date": "2001-01-01"},
    ]
    with patch(SEND) as mock_send:
        resp = client.post("/documents/import/commit", json={"rows": rows})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["created_count"], data["skipped_count"], data["error_count"]) == (3, 1, 1)
    assert data["emails_sent"] == 2
    assert sorted(len(c.args[0]) for c in mock_send.call_args_list) == [1, 2]

    session = SessionLocal()
    try:
        new_clients = session.query(DocumentClient).filter(DocumentClient.email == new_email).all()
        assert len(new_clients) == 1  # second row reused the client created by the first
    finally:
        session.close()
    assert sorted(r.title for r in _requests_for(existing_id)) == ["Payslip", "Tax return"]


def test_import_rejects_xlsx_that_unpacks_to_huge_size():
    """A tiny upload can be a zip bomb; refuse before openpyxl inflates it."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (60 * 1024 * 1024))
    raw = buf.getvalue()
    assert len(raw) < 1024 * 1024  # small on the wire
    resp = client.post("/documents/import/preview", files={"file": ("bomb.xlsx", raw,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"]
