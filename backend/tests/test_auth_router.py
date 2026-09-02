import base64
import hashlib
import json
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

import pytest
from crypto_utils import decrypt_payload, ENCRYPTION_KEY, _evp_bytes_to_key

def helper_encrypt_payload(data: dict, key: str = ENCRYPTION_KEY) -> str:
    """Helper function replicating frontend OpenSSL EVP_BytesToKey AES encryption."""
    json_bytes = json.dumps(data).encode("utf-8")
    salt = os.urandom(8)
    derived_key, iv = _evp_bytes_to_key(key.encode("utf-8"), salt, 32, 16)
    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    padded = pad(json_bytes, AES.block_size)
    ciphertext = cipher.encrypt(padded)
    raw = b"Salted__" + salt + ciphertext
    return base64.b64encode(raw).decode("utf-8")

def test_decrypt_payload_success():
    payload = {"username": "testuser", "email": "test@example.com", "password": "password123"}
    encrypted_str = helper_encrypt_payload(payload)
    decrypted = decrypt_payload(encrypted_str)
    assert decrypted == payload

def test_decrypt_payload_invalid_format():
    with pytest.raises(ValueError, match="Invalid encrypted data format"):
        decrypt_payload(base64.b64encode(b"NotSaltedData").decode("utf-8"))
