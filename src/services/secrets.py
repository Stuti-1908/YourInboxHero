"""Symmetric encryption for at-rest secrets we must later decrypt and use
ourselves — currently just customer SMTP passwords (src/models/user.py's
User.smtp_password). NOT for user account passwords, which stay one-way
hashed via passlib in src/auth.py and must never be decryptable.

Uses Fernet (AES-128-CBC + HMAC, from the `cryptography` package) with a
single key from settings.encryption_key. Losing that key makes every
already-encrypted value permanently undecryptable, so it must be backed
up the same way SECRET_KEY is.
"""
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config.settings import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    if not settings.encryption_key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not configured — cannot encrypt/decrypt stored secrets. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.encryption_key.encode())


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a value for storage. None passes through unchanged (so
    callers can encrypt an Optional[str] field without a branch)."""
    if plaintext is None:
        return None
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a stored value. None passes through unchanged. Returns None
    (rather than raising) on a value that fails to decrypt — e.g. a stale
    plaintext value from before this encryption was introduced — since the
    caller's job is to treat "no usable credential" the same way whether
    the field is empty or corrupt, not to crash a reminder send over it."""
    if ciphertext is None:
        return None
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None
