"""Cryptographic utilities for sensitive token encryption."""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from velopulse.core.config import get_settings


@lru_cache
def get_fernet_cipher() -> Fernet:
    """Retrieve or derive a Fernet symmetric cipher instance.

    Uses `settings.ENCRYPTION_KEY` if provided (must be 32 url-safe base64 bytes).
    Otherwise, derives a deterministic 32-byte key from `settings.SECRET_KEY`
    using SHA-256 and url-safe base64 encoding.
    """
    settings = get_settings()
    if hasattr(settings, "ENCRYPTION_KEY") and settings.ENCRYPTION_KEY:
        try:
            return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))
        except Exception:
            pass

    # Deterministic fallback derivation from SECRET_KEY
    derived_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(derived_bytes)
    return Fernet(fernet_key)


def encrypt_token(raw_token: str) -> str:
    """Encrypt a sensitive token string into a safe ciphertext string.

    Args:
        raw_token: Plaintext secret (e.g. Strava OAuth refresh token).

    Returns:
        URL-safe encrypted string representation.
    """
    if not raw_token:
        return ""
    cipher = get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(raw_token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a ciphertext string back to the plaintext secret.

    Args:
        encrypted_token: Encrypted ciphertext string.

    Returns:
        Plaintext secret.

    Raises:
        ValueError: If ciphertext is corrupt or key does not match.
    """
    if not encrypted_token:
        return ""
    cipher = get_fernet_cipher()
    try:
        decrypted_bytes = cipher.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid or corrupted ciphertext token.") from exc
