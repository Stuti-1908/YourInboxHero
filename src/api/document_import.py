"""Bulk document requests: one form submission or one CSV/Excel upload can
ask a client for several documents at once.

Both paths end in the same place -- requests created, then ONE email per
client listing every new document with its own upload link -- so a
client asked for five documents gets one email, not five.

  POST /documents/batch            one client (existing or new) + N titles
  POST /documents/import/preview   parse + validate a CSV/.xlsx, write nothing
  POST /documents/import/commit    create the previewed rows (re-validated)

Import columns (header row required, case-insensitive):
  client_name, client_email, document_title, due_date (YYYY-MM-DD),
  client_phone (optional), description (optional)
"""
import re
from collections import OrderedDict
from datetime import date, datetime
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.auth import require_active_subscription
from src.db import get_db
from src.models.document_client import DocumentClient
from src.models.document_request import DocumentRequest
from src.models.user import User
from src.services.tabular import read_table

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="", tags=["documents"])

MAX_TITLES_PER_REQUEST = 20
MAX_IMPORT_ROWS = 1000
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
REQUIRED_COLUMNS = {"client_name", "client_email", "document_title", "due_date"}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Statuses where the client still owes the document -- asking again for the
# same title would just duplicate the chase.
_OPEN_STATUSES = ("pending", "overdue")


class NewClient(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    voice_call_consent: bool = False


class DocumentBatchCreate(BaseModel):
    client_id: Optional[str] = None
    client: Optional[NewClient] = None
    titles: List[str]
    description: Optional[str] = None
    due_date: date


class CreatedRequest(BaseModel):
    id: str
    title: str
    due_date: date
    status: str
    upload_token: str


class DocumentBatchResponse(BaseModel):
    client_id: str
    client_name: str
    client_email: str
    requests: List[CreatedRequest]
    email_sent: bool


class DocImportRow(BaseModel):
    row_number: int  # spreadsheet row; header is row 1
    client_name: str
    client_email: str
    client_phone: Optional[str] = None
    document_title: str
    due_date: date
    description: Optional[str] = None
    client_exists: bool = False  # preview-only hint; commit re-checks


class DocImportRowError(BaseModel):
    row_number: int
    error: str


class DocImportPreviewResponse(BaseModel):
    valid_rows: List[DocImportRow]
    errors: List[DocImportRowError]
    total_rows: int


class DocImportCommitRequest(BaseModel):
    rows: List[DocImportRow]


class DocImportCommitResult(BaseModel):
    row_number: int
    status: str  # "created" | "skipped" | "error"
    detail: str


class DocImportCommitResponse(BaseModel):
    results: List[DocImportCommitResult]
    created_count: int
    skipped_count: int
    error_count: int
    emails_sent: int
    emails_failed: int


def _normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def _find_client_by_email(db: Session, user_id: str, email: str) -> Optional[DocumentClient]:
    # Emails may have been stored with mixed case before this module
    # normalised them, so compare case-insensitively.
    return db.query(DocumentClient).filter(
        DocumentClient.user_id == user_id,
        func.lower(DocumentClient.email) == email,
    ).order_by(DocumentClient.created_at).first()


def _open_titles(db: Session, client_id: str) -> set:
    rows = db.query(DocumentRequest.title).filter(
        DocumentRequest.client_id == client_id,
        DocumentRequest.status.in_(_OPEN_STATUSES),
    ).all()
    return {t.strip().lower() for (t,) in rows}


def _send_grouped_emails(docs_by_client: "OrderedDict[str, List[DocumentRequest]]") -> tuple[int, int]:
    """Best-effort: one email per client. A failed send never undoes the
    created requests -- the upload links still exist and can be copied
    from the dashboard, same reasoning as the single-request endpoint."""
    from src.services.document_email import send_document_request_email

    sent = failed = 0
    for client_id, docs in docs_by_client.items():
        if not docs:
            continue
        try:
            send_document_request_email(docs)
            sent += 1
        except Exception as exc:
            failed += 1
            logger.error("document_batch_email_failed", client_id=client_id,
                         doc_request_ids=[d.id for d in docs], error=str(exc))
    return sent, failed


@router.post("/documents/batch", response_model=DocumentBatchResponse)
def create_document_batch(
    data: DocumentBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Request one or more documents from one client in a single step.
    The client is either an existing one (client_id) or created inline
    (client); an inline client whose email already exists is reused rather
    than duplicated."""
    if bool(data.client_id) == bool(data.client):
        raise HTTPException(status_code=422, detail="Choose an existing client or enter a new one (not both)")

    titles: List[str] = []
    seen = set()
    for raw in data.titles:
        t = (raw or "").strip()
        if not t or t.lower() in seen:
            continue
        if len(t) > MAX_TITLE_LENGTH:
            raise HTTPException(status_code=422, detail=f"Document name is too long (max {MAX_TITLE_LENGTH} characters): '{t[:40]}...'")
        seen.add(t.lower())
        titles.append(t)
    if not titles:
        raise HTTPException(status_code=422, detail="Add at least one document to request")
    if len(titles) > MAX_TITLES_PER_REQUEST:
        raise HTTPException(status_code=422, detail=f"You can request up to {MAX_TITLES_PER_REQUEST} documents at once")
    if data.due_date < date.today():
        raise HTTPException(status_code=422, detail="Due date can't be in the past")

    if data.client_id:
        client = db.query(DocumentClient).filter(
            DocumentClient.id == data.client_id,
            DocumentClient.user_id == current_user.id,
        ).first()
        if not client:
            raise HTTPException(status_code=404, detail="Document client not found")
    else:
        nc = data.client
        name = nc.name.strip()
        email = _normalise_email(nc.email)
        phone = (nc.phone or "").strip() or None
        if not name:
            raise HTTPException(status_code=422, detail="Client name is required")
        if not _EMAIL_RE.match(email):
            raise HTTPException(status_code=422, detail="Enter a valid client email address")
        if nc.voice_call_consent and not phone:
            raise HTTPException(status_code=422, detail="A phone number is required to record voice call consent")
        client = _find_client_by_email(db, current_user.id, email)
        if client is None:
            client = DocumentClient(
                user_id=current_user.id, name=name, email=email,
                phone=phone, voice_call_consent=nc.voice_call_consent,
            )
            db.add(client)
            db.flush()
        else:
            # Fill gaps on the existing record, never overwrite what's there.
            if phone and not client.phone:
                client.phone = phone
            # Consent is only recorded for the number the user actually
            # typed -- never transferred onto a different stored number.
            if nc.voice_call_consent and phone and client.phone == phone:
                client.voice_call_consent = True

    already_open = _open_titles(db, client.id)
    duplicates = [t for t in titles if t.lower() in already_open]
    if duplicates:
        raise HTTPException(
            status_code=409,
            detail=f"Already waiting on {', '.join(duplicates)} from {client.name}",
        )

    description = (data.description or "").strip() or None
    if description and len(description) > MAX_DESCRIPTION_LENGTH:
        raise HTTPException(status_code=422, detail=f"Note is too long (max {MAX_DESCRIPTION_LENGTH} characters)")
    docs = []
    for t in titles:
        doc = DocumentRequest(
            user_id=current_user.id, client_id=client.id, title=t,
            description=description, due_date=data.due_date, status="pending",
        )
        db.add(doc)
        docs.append(doc)
    db.commit()
    for d in docs:
        db.refresh(d)

    sent, _ = _send_grouped_emails(OrderedDict([(client.id, docs)]))

    return DocumentBatchResponse(
        client_id=client.id,
        client_name=client.name,
        client_email=client.email,
        requests=[
            CreatedRequest(id=d.id, title=d.title, due_date=d.due_date, status=d.status, upload_token=d.upload_token)
            for d in docs
        ],
        email_sent=sent == 1,
    )


def _parse_import_rows(raw: bytes, filename: str) -> tuple[List[dict], List[DocImportRowError]]:
    headers, table_rows = read_table(raw, filename)
    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"File is missing required column(s): {', '.join(sorted(missing))}",
        )

    rows: List[dict] = []
    errors: List[DocImportRowError] = []
    seen = set()
    today = date.today()

    for n, row in enumerate(table_rows, start=1):
        i = row.pop("__row__")  # true spreadsheet row, header = row 1
        if n > MAX_IMPORT_ROWS:
            errors.append(DocImportRowError(row_number=i, error=f"Exceeds max {MAX_IMPORT_ROWS} rows per import — split into multiple files"))
            break

        name = row.get("client_name", "")
        email = _normalise_email(row.get("client_email", ""))
        title = row.get("document_title", "")
        due_raw = row.get("due_date", "")

        if not name or not email or not title or not due_raw:
            errors.append(DocImportRowError(
                row_number=i,
                error="Missing a required value (client_name, client_email, document_title, or due_date)",
            ))
            continue
        if not _EMAIL_RE.match(email):
            errors.append(DocImportRowError(row_number=i, error=f"'{email}' doesn't look like a valid email"))
            continue
        if len(title) > MAX_TITLE_LENGTH:
            errors.append(DocImportRowError(row_number=i, error=f"document_title is longer than {MAX_TITLE_LENGTH} characters"))
            continue
        if len(row.get("description", "")) > MAX_DESCRIPTION_LENGTH:
            errors.append(DocImportRowError(row_number=i, error=f"description is longer than {MAX_DESCRIPTION_LENGTH} characters"))
            continue
        try:
            due = datetime.strptime(due_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append(DocImportRowError(row_number=i, error=f"Invalid due_date: '{due_raw}' (expected YYYY-MM-DD)"))
            continue
        if due < today:
            errors.append(DocImportRowError(row_number=i, error=f"due_date {due_raw} is in the past"))
            continue

        key = (email, title.lower())
        if key in seen:
            errors.append(DocImportRowError(row_number=i, error=f"'{title}' for {email} appears more than once in this file"))
            continue
        seen.add(key)

        rows.append({
            "row_number": i,
            "client_name": name,
            "client_email": email,
            "client_phone": row.get("client_phone") or None,
            "document_title": title,
            "due_date": due,
            "description": row.get("description") or None,
        })
    return rows, errors


@router.post("/documents/import/preview", response_model=DocImportPreviewResponse)
async def preview_document_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Parse and validate a CSV/.xlsx without writing anything."""
    raw = await file.read()
    parsed, errors = _parse_import_rows(raw, file.filename or "import.csv")

    clients_by_email = {
        _normalise_email(c.email): c
        for c in db.query(DocumentClient).filter(DocumentClient.user_id == current_user.id).all()
    }
    open_titles_cache: dict = {}

    valid: List[DocImportRow] = []
    for r in parsed:
        client = clients_by_email.get(r["client_email"])
        if client is not None:
            if client.id not in open_titles_cache:
                open_titles_cache[client.id] = _open_titles(db, client.id)
            if r["document_title"].lower() in open_titles_cache[client.id]:
                errors.append(DocImportRowError(
                    row_number=r["row_number"],
                    error=f"Already waiting on '{r['document_title']}' from {r['client_email']}",
                ))
                continue
        valid.append(DocImportRow(**r, client_exists=client is not None))

    errors.sort(key=lambda e: e.row_number)
    return DocImportPreviewResponse(valid_rows=valid, errors=errors, total_rows=len(parsed) + len(errors))


@router.post("/documents/import/commit", response_model=DocImportCommitResponse)
def commit_document_import(
    request: DocImportCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_active_subscription),
):
    """Create previewed rows, then send one email per client. Re-validates
    against the live DB rather than trusting the preview payload."""
    if len(request.rows) > MAX_IMPORT_ROWS:
        raise HTTPException(status_code=400, detail=f"Cannot import more than {MAX_IMPORT_ROWS} rows at once")

    results: List[DocImportCommitResult] = []
    created = skipped = errored = 0
    client_cache: dict = {}
    open_titles_cache: dict = {}
    created_by_client: "OrderedDict[str, List[DocumentRequest]]" = OrderedDict()
    today = date.today()

    for row in request.rows:
        email = _normalise_email(row.client_email)
        title = row.document_title.strip()
        name = row.client_name.strip()
        if (not name or not title or not _EMAIL_RE.match(email) or len(title) > MAX_TITLE_LENGTH
                or len(row.description or "") > MAX_DESCRIPTION_LENGTH or row.due_date < today):
            results.append(DocImportCommitResult(row_number=row.row_number, status="error", detail="Row failed validation"))
            errored += 1
            continue

        savepoint = db.begin_nested()
        try:
            client = client_cache.get(email) or _find_client_by_email(db, current_user.id, email)
            if client is None:
                client = DocumentClient(
                    user_id=current_user.id, name=name, email=email,
                    phone=(row.client_phone or "").strip() or None,
                )
                db.add(client)
                db.flush()
            client_cache[email] = client

            if client.id not in open_titles_cache:
                open_titles_cache[client.id] = _open_titles(db, client.id)
            if title.lower() in open_titles_cache[client.id]:
                savepoint.rollback()
                results.append(DocImportCommitResult(
                    row_number=row.row_number, status="skipped",
                    detail=f"Already waiting on '{title}' from {email}",
                ))
                skipped += 1
                continue

            doc = DocumentRequest(
                user_id=current_user.id, client_id=client.id, title=title,
                description=(row.description or "").strip() or None,
                due_date=row.due_date, status="pending",
            )
            db.add(doc)
            db.flush()
            savepoint.commit()

            open_titles_cache[client.id].add(title.lower())
            created_by_client.setdefault(client.id, []).append(doc)
            results.append(DocImportCommitResult(
                row_number=row.row_number, status="created", detail=f"Requested '{title}' from {email}",
            ))
            created += 1
        except Exception as exc:
            savepoint.rollback()
            # Drop a client created inside the rolled-back savepoint from the
            # cache so the next row for that email doesn't reference it.
            client_cache.pop(email, None)
            results.append(DocImportCommitResult(row_number=row.row_number, status="error", detail=str(exc)))
            errored += 1

    db.commit()
    for docs in created_by_client.values():
        for d in docs:
            db.refresh(d)

    emails_sent, emails_failed = _send_grouped_emails(created_by_client)

    return DocImportCommitResponse(
        results=results,
        created_count=created,
        skipped_count=skipped,
        error_count=errored,
        emails_sent=emails_sent,
        emails_failed=emails_failed,
    )
