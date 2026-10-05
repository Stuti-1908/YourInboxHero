"""Local-disk storage for client-uploaded documents (W-9s, signed contracts,
etc.). Files are written under settings.upload_dir, which must be backed
by a persistent volume in production (see docker-compose.yml) or they are
lost on every redeploy.

Each file is stored under a path derived from the DocumentRequest's id
rather than the original filename, so two requests can't collide and a
client can't control the on-disk path via a crafted filename.
"""
import os
import re
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException

from src.config.settings import get_settings

# Deliberately narrow — this is for business documents (tax forms,
# contracts, IDs), not general file upload. Expand only if a real need
# for another type comes up.
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext or 'unknown'}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


async def save_uploaded_document(document_request_id: str, file: UploadFile) -> tuple[str, str]:
    """Validate and persist an uploaded file. Returns (stored_filename, original_filename).

    Raises HTTPException(400) for an unsupported type or oversized file.
    """
    settings = get_settings()

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type '{file.content_type}'. Allowed: PDF, PNG, JPEG, DOC, DOCX",
        )
    ext = _safe_extension(file.filename or "")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds the {settings.max_upload_size_mb}MB limit")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # document_request_id is a UUID we generated, safe to use directly; a
    # random suffix is added so a resubmission never silently overwrites
    # the previous file before anyone has looked at it.
    stored_filename = f"{document_request_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = upload_dir / stored_filename

    with open(dest_path, "wb") as f:
        f.write(contents)

    original_filename = os.path.basename(file.filename or "document")
    return stored_filename, original_filename


def get_document_path(stored_filename: str) -> Path:
    """Resolve a stored filename back to its path, guarding against path
    traversal — stored_filename is expected to be exactly what
    save_uploaded_document generated, but this is defense in depth since
    it ultimately comes from a DB column, not hardcoded."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir).resolve()

    # Reject anything with path separators or '..' outright rather than
    # relying solely on the resolved-path containment check below.
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9]+", stored_filename):
        raise HTTPException(status_code=400, detail="Invalid file reference")

    candidate = (upload_dir / stored_filename).resolve()
    if upload_dir not in candidate.parents and candidate != upload_dir:
        raise HTTPException(status_code=400, detail="Invalid file reference")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return candidate
