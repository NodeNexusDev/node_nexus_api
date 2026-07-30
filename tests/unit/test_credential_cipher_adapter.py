"""Tests for the credential cipher adapter."""

from unittest.mock import patch

from app.adapters.security import AesGcmCredentialCipher


def test_encrypt_delegates_to_aes_gcm_implementation() -> None:
    with patch(
        "app.adapters.security.credential_cipher.encrypt",
        return_value="enc:v1:ciphertext",
    ) as encrypt:
        result = AesGcmCredentialCipher().encrypt("secret")

    assert result == "enc:v1:ciphertext"
    encrypt.assert_called_once_with("secret")


def test_decrypt_preserves_legacy_compatibility_policy() -> None:
    with patch(
        "app.adapters.security.credential_cipher.decrypt_value",
        return_value="secret",
    ) as decrypt:
        result = AesGcmCredentialCipher().decrypt("enc:v1:ciphertext")

    assert result == "secret"
    decrypt.assert_called_once_with("enc:v1:ciphertext")
