"""CSV bulk import for debtors + invoices.

Two-step flow: the frontend uploads the CSV to /preview first, which
parses and validates every row without writing anything to the DB and
returns back exactly what would be created (plus any row-level errors) so
the user can review before committing. /commit takes that same parsed
row data back and actually creates the records, re-validating everything
server-side rather than trusting whatever the frontend sends back (the
preview step is a UX convenience, not a security boundary).

Expected CSV columns (header row required, case-insensitive):
  debtor_name, debtor_email, debtor_phone (optional),
  invoice_number, amount, due_date (YYYY-MM-DD), description (optional)

One row per invoice; a debtor is matched by email (scoped to the current
user) or created if no existing debtor has that email yet.
"""
import csv
import io
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.db import get_db
from src.auth import get_current_user
from src.models.user import User
from src.models.debtor import Debtor
from src.models.invoice import Invoice, InvoiceStatus

router = APIRouter()

REQUIRED_COLUMNS = {"debtor_name", "debtor_email", "invoice_number", "amount", "due_date"}
MAX_ROWS = 1000  # sanity cap — a CSV this large likely needs a different workflow anyway


class ImportRow(BaseModel):
    row_number: int  # 1-indexed, matching what a user sees opening the CSV in a spreadsheet (header = row 1)
    debtor_name: str
    debtor_email: str
    debtor_phone: Optional[str] = None
    invoice_number: str
    amount: float
    due_date: date
    description: Optional[str] = None
    # Preview-only hints for the UI — not re-derived from trusted state,
    # just a best-effort "this debtor already exists" signal at preview
    # time; commit always re-checks against the DB at write time.
    debtor_exists: bool = False


class ImportRowError(BaseModel):
    row_number: int
    error: str


class ImportPreviewResponse(BaseModel):
    valid_rows: List[ImportRow]
    errors: List[ImportRowError]
    total_rows: int


class ImportCommitRequest(BaseModel):
    rows: List[ImportRow]


class ImportCommitResult(BaseModel):
    row_number: int
    status: str  # "created" | "skipped" | "error"
    detail: str
    invoice_id: Optional[str] = None


class ImportCommitResponse(BaseModel):
    results: List[ImportCommitResult]
    created_count: int
    skipped_count: int
    error_count: int


def _parse_csv_rows(raw: bytes) -> tuple[List[dict], List[ImportRowError]]:
    """Parse + structurally validate every row. Returns (parsed_dicts, errors).
    A row with an error is excluded from parsed_dicts."""
    try:
        text = raw.decode("utf-8-sig")  # handles Excel's BOM-prefixed UTF-8 exports
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required column(s): {', '.join(sorted(missing))}",
        )

    rows: List[dict] = []
    errors: List[ImportRowError] = []
    seen_invoice_numbers_in_file = set()

    for i, raw_row in enumerate(reader, start=2):  # row 1 is the header
        if i - 1 > MAX_ROWS:
            errors.append(ImportRowError(row_number=i, error=f"Exceeds max {MAX_ROWS} rows per import — split into multiple files"))
            break

        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}

        name = row.get("debtor_name", "")
        email = row.get("debtor_email", "")
        invoice_number = row.get("invoice_number", "")
        amount_raw = row.get("amount", "")
        due_date_raw = row.get("due_date", "")

        if not name or not email or not invoice_number or not amount_raw or not due_date_raw:
            errors.append(ImportRowError(
                row_number=i,
                error="Missing a required value (debtor_name, debtor_email, invoice_number, amount, or due_date)",
            ))
            continue

        if "@" not in email:
            errors.append(ImportRowError(row_number=i, error=f"'{email}' doesn't look like a valid email"))
            continue

        try:
            amount = float(amount_raw.replace("$", "").replace(",", ""))
            if amount <= 0:
                raise ValueError()
        except ValueError:
            errors.append(ImportRowError(row_number=i, error=f"Invalid amount: '{amount_raw}'"))
            continue

        try:
            due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append(ImportRowError(row_number=i, error=f"Invalid due_date: '{due_date_raw}' (expected YYYY-MM-DD)"))
            continue

        if invoice_number in seen_invoice_numbers_in_file:
            errors.append(ImportRowError(row_number=i, error=f"Duplicate invoice_number '{invoice_number}' within this file"))
            continue
        seen_invoice_numbers_in_file.add(invoice_number)

        rows.append({
            "row_number": i,
            "debtor_name": name,
            "debtor_email": email,
            "debtor_phone": row.get("debtor_phone") or None,
            "invoice_number": invoice_number,
            "amount": amount,
            "due_date": due_date,
            "description": row.get("description") or None,
        })

    return rows, errors


@router.post("/invoice/import/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse and validate a CSV without writing anything to the database."""
    raw = await file.read()
    parsed_rows, errors = _parse_csv_rows(raw)

    # Cross-reference existing invoice numbers and debtors for this user so
    # the preview can flag likely duplicates before commit.
    existing_invoice_numbers = {
        n for (n,) in db.query(Invoice.invoice_number)
        .filter(Invoice.user_id == current_user.id)
        .all()
    }
    existing_debtor_emails = {
        e for (e,) in db.query(Debtor.email).filter(Debtor.user_id == current_user.id).all()
    }

    valid_rows: List[ImportRow] = []
    for r in parsed_rows:
        if r["invoice_number"] in existing_invoice_numbers:
            errors.append(ImportRowError(
                row_number=r["row_number"],
                error=f"Invoice number '{r['invoice_number']}' already exists in your account",
            ))
            continue
        valid_rows.append(ImportRow(
            **r,
            debtor_exists=r["debtor_email"] in existing_debtor_emails,
        ))

    return ImportPreviewResponse(
        valid_rows=valid_rows,
        errors=errors,
        total_rows=len(parsed_rows) + len(errors),
    )


@router.post("/invoice/import/commit", response_model=ImportCommitResponse)
def commit_import(
    request: ImportCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create the debtors/invoices for a previously previewed set of rows.
    Re-validates everything against the live DB rather than trusting the
    preview response, since state may have changed between the two calls
    (e.g. another request created a conflicting invoice number)."""
    if len(request.rows) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"Cannot import more than {MAX_ROWS} rows at once")

    results: List[ImportCommitResult] = []
    created_count = 0
    skipped_count = 0
    error_count = 0

    # Cache debtors created/matched during this commit so multiple invoice
    # rows for the same debtor_email reuse one Debtor instead of erroring
    # on the second row (unique email constraint).
    debtor_cache: dict[str, Debtor] = {}

    for row in request.rows:
        savepoint = db.begin_nested()
        try:
            if db.query(Invoice).filter(Invoice.invoice_number == row.invoice_number, Invoice.user_id == current_user.id).first():
                savepoint.rollback()
                results.append(ImportCommitResult(
                    row_number=row.row_number, status="skipped",
                    detail=f"Invoice number '{row.invoice_number}' already exists",
                ))
                skipped_count += 1
                continue

            debtor = debtor_cache.get(row.debtor_email)
            if debtor is None:
                debtor = (
                    db.query(Debtor)
                    .filter(Debtor.email == row.debtor_email, Debtor.user_id == current_user.id)
                    .first()
                )
            if debtor is None:
                debtor = Debtor(
                    user_id=current_user.id,
                    name=row.debtor_name,
                    email=row.debtor_email,
                    phone=row.debtor_phone,
                    debtor_type="business",
                )
                db.add(debtor)
                db.flush()
            debtor_cache[row.debtor_email] = debtor

            status = InvoiceStatus.upcoming
            if row.due_date < date.today():
                status = InvoiceStatus.overdue
            elif row.due_date == date.today():
                status = InvoiceStatus.due

            invoice = Invoice(
                user_id=current_user.id,
                debtor_id=debtor.id,
                invoice_number=row.invoice_number,
                amount=row.amount,
                description=row.description,
                due_date=row.due_date,
                status=status,
            )
            db.add(invoice)
            db.flush()

            savepoint.commit()
            results.append(ImportCommitResult(
                row_number=row.row_number, status="created",
                detail=f"Created invoice {row.invoice_number}", invoice_id=invoice.id,
            ))
            created_count += 1

        except Exception as exc:
            savepoint.rollback()
            results.append(ImportCommitResult(
                row_number=row.row_number, status="error", detail=str(exc),
            ))
            error_count += 1
            continue

    db.commit()

    return ImportCommitResponse(
        results=results,
        created_count=created_count,
        skipped_count=skipped_count,
        error_count=error_count,
    )
