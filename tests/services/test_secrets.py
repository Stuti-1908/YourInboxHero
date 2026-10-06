"""Tests for src/services/secrets.py — the SMTP-password-at-rest encryption."""
from src.services.secrets import encrypt_secret, decrypt_secret


def test_encrypt_then_decrypt_roundtrips():
    plaintext = "my-smtp-app-password-123"
    ciphertext = encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert decrypt_secret(ciphertext) == plaintext


def test_encrypt_none_returns_none():
    assert encrypt_secret(None) is None


def test_decrypt_none_returns_none():
    assert decrypt_secret(None) is None


def test_decrypt_garbage_returns_none_not_raises():
    """A stale plaintext value from before encryption was introduced, or
    any other non-Fernet string, must fail closed (no usable credential)
    rather than crash whatever's trying to send email."""
    assert decrypt_secret("this-was-never-encrypted") is None


def test_ciphertext_is_not_the_plaintext_substring():
    """Sanity check that this isn't a no-op encoding like base64 of the
    plaintext — the whole point is the stored value must not reveal the
    credential even to someone with read access to the database."""
    plaintext = "SuperSecretPassword!"
    ciphertext = encrypt_secret(plaintext)
    assert plaintext not in ciphertext
