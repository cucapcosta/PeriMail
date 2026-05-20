import os
import pytest
from perimail.crypto import decrypt, encrypt


@pytest.fixture
def key():
    return os.urandom(32)


def test_encrypt_decrypt_roundtrip(key):
    plaintext = '{"access_token": "ya29.xxx", "refresh_token": "1//yyy"}'
    assert decrypt(encrypt(plaintext, key), key) == plaintext


def test_different_ciphertexts_same_plaintext(key):
    token1 = encrypt("same", key)
    token2 = encrypt("same", key)
    assert token1 != token2  # different random nonces


def test_wrong_key_raises(key):
    token = encrypt("secret", key)
    with pytest.raises(Exception):
        decrypt(token, os.urandom(32))


def test_tampered_ciphertext_raises(key):
    token = encrypt("secret", key)
    tampered = token[:-4] + "XXXX"
    with pytest.raises(Exception):
        decrypt(tampered, key)
