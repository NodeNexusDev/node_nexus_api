"""Unit tests for security encryption edge cases."""

import base64

import pytest

from app.adapters.security.credential_cipher import ENCRYPTION_PREFIX, decrypt, encrypt


class TestEncryptDecrypt:
    def test_empty_string(self) -> None:
        encrypted = encrypt("")
        assert encrypted.startswith(ENCRYPTION_PREFIX)
        assert decrypt(encrypted) == ""

    def test_unicode_string(self) -> None:
        text = "привет мир 🌍"
        assert decrypt(encrypt(text)) == text

    def test_long_string(self) -> None:
        text = "x" * 10_000
        assert decrypt(encrypt(text)) == text

    def test_special_characters(self) -> None:
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        assert decrypt(encrypt(text)) == text

    def test_newlines_and_tabs(self) -> None:
        text = "line1\nline2\ttab"
        assert decrypt(encrypt(text)) == text

    def test_different_ciphertext_each_time(self) -> None:
        text = "same-input"
        c1 = encrypt(text)
        c2 = encrypt(text)
        assert c1 != c2
        assert decrypt(c1) == text
        assert decrypt(c2) == text

    def test_decrypt_tampered_ciphertext(self) -> None:
        encrypted = encrypt("secret")
        payload = encrypted.removeprefix(ENCRYPTION_PREFIX)
        raw = base64.b64decode(payload)
        tampered = ENCRYPTION_PREFIX + base64.b64encode(raw[:-1] + b"\x00").decode()
        with pytest.raises(Exception):
            decrypt(tampered)

    def test_decrypt_invalid_base64(self) -> None:
        with pytest.raises(Exception):
            decrypt("not-valid-base64!!!")

    def test_decrypt_too_short(self) -> None:
        short = base64.b64encode(b"tiny").decode()
        with pytest.raises(Exception):
            decrypt(short)
