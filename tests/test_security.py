"""Tests for token encryption and cryptographic helpers."""

import pytest

from velopulse.core.security import decrypt_token, encrypt_token


def test_token_encryption_roundtrip() -> None:
    """Verify raw tokens can be encrypted and decrypted accurately."""
    original_token = "c4b928f09d84638ba1a88e20e8b35041a7d18bc9"
    encrypted = encrypt_token(original_token)

    assert encrypted != original_token
    assert len(encrypted) > len(original_token)

    decrypted = decrypt_token(encrypted)
    assert decrypted == original_token


def test_token_encryption_empty() -> None:
    """Verify empty or None tokens return empty string."""
    assert encrypt_token("") == ""
    assert decrypt_token("") == ""


def test_token_encryption_randomized_ciphertext() -> None:
    """Verify Fernet generates distinct ciphertexts for identical plaintext."""
    token = "fixed_token_value_123"
    enc_1 = encrypt_token(token)
    enc_2 = encrypt_token(token)

    assert enc_1 != enc_2
    assert decrypt_token(enc_1) == token
    assert decrypt_token(enc_2) == token


def test_token_decryption_corrupt_fails() -> None:
    """Verify corrupt ciphertext raises ValueError."""
    corrupt_token = "gAAAAABl8invalidciphertextnotvalidbase64=="
    with pytest.raises(ValueError, match="Invalid or corrupted"):
        decrypt_token(corrupt_token)
