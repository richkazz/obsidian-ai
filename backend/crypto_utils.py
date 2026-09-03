import base64
import hashlib
import json
import os
import re
from typing import Any
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")


def decrypt_payload(encrypted_data: str) -> dict:
    """
    Decrypt data encrypted by CryptoJS AES.
    CryptoJS uses OpenSSL-compatible format with "Salted__" prefix.
    """
    raw = base64.b64decode(encrypted_data)

    if raw[:8] != b"Salted__":
        raise ValueError("Invalid encrypted data format")

    salt = raw[8:16]
    ciphertext = raw[16:]

    encryption_key = os.getenv("ENCRYPTION_KEY", ENCRYPTION_KEY)
    key, iv = _evp_bytes_to_key(encryption_key.encode(), salt, 32, 16)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)

    return json.loads(decrypted.decode("utf-8"))


# ── Telemetry & Trace Sanitization ──────────────────────────────────────────────

_BEARER_KEY_RE = re.compile(
    r"(Bearer\s+|x-api-key\s*:\s*|authorization\s*:\s*|gAAAAA)[A-Za-z0-9_\-\.\=]+",
    re.IGNORECASE,
)
_SENSITIVE_FIELD_RE = re.compile(
    r'"(api_key|authorization|x-api-key|x-api-secret|secret|password|token|ciphertext|fernet_key)":\s*"[^"]*"',
    re.IGNORECASE,
)


def sanitize_trace_data(data: Any) -> str:
    """
    Sanitize trace attribute data before exporting or storing in trace_spans table.
    Strips Authorization headers, X-API-Key, X-API-Secret, and Fernet ciphertexts.
    """
    if data is None:
        return ""
    if not isinstance(data, str):
        try:
            data = json.dumps(data)
        except Exception:
            data = str(data)

    data = _SENSITIVE_FIELD_RE.sub(r'"\1": "[REDACTED]"', data)
    data = _BEARER_KEY_RE.sub(r"\1[REDACTED]", data)
    return data


def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int, iv_len: int):
    """
    OpenSSL EVP_BytesToKey key derivation function.
    Used by CryptoJS for password-based encryption.
    """
    dtot = b""
    d = b""
    while len(dtot) < key_len + iv_len:
        d = hashlib.md5(d + password + salt).digest()
        dtot += d
    return dtot[:key_len], dtot[key_len:key_len + iv_len]
