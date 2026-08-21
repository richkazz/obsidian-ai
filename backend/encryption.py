"""
encryption.py — API key encryption at rest.

Two layers:
  1. Global Fernet key (PROVIDER_KEY_SECRET env var) — master key that wraps
     per-user keys and decrypts legacy ciphertext.
  2. Per-user envelope encryption — each user has a unique 32-byte AES-256-GCM
     key stored in the `user_keys` collection, itself wrapped with the global
     Fernet key. New writes use encrypt_for_user() / decrypt_for_user().
     Existing legacy ciphertext is transparently decrypted via the global key.

Callers with user_id + mongo_db available (providers, secrets, 2FA TOTP):
    await encrypt_for_user(value, user_id, mongo_db)
    await decrypt_for_user(ciphertext, user_id, mongo_db)

Callers without user_id (schedulers, background workers, legacy paths):
    encrypt_api_key(value)    — global Fernet
    decrypt_api_key(value)    — global Fernet (works on both legacy + new ciphertext
                                if the value is not per-user; per-user ciphertext
                                must use decrypt_for_user)
"""

import os
import base64
import secrets as _secrets
from cryptography.fernet import Fernet

# ── Master key ────────────────────────────────────────────────────────────────

_master_key_str = os.getenv("PROVIDER_KEY_SECRET")
if not _master_key_str:
    _master_key_str = Fernet.generate_key().decode()

_master_fernet = Fernet(
    _master_key_str.encode() if isinstance(_master_key_str, str) else _master_key_str
)

# Keep the old name so any direct `fernet` references still work
fernet = _master_fernet


# ── Legacy / global-key helpers (unchanged API) ───────────────────────────────

def encrypt_api_key(api_key: str) -> str:
    """Encrypt with the global master Fernet key. Legacy / background-worker path."""
    return _master_fernet.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt with the global master Fernet key. Legacy / background-worker path."""
    return _master_fernet.decrypt(encrypted_key.encode()).decode()


# ── Per-user envelope encryption ─────────────────────────────────────────────

_USER_KEYS_COLLECTION = "user_keys"
_PER_USER_PREFIX = "uk1:"   # marks AES-GCM per-user ciphertext


def _wrap_user_key(raw_key_bytes: bytes) -> str:
    """Fernet-encrypt a 32-byte user key for storage."""
    return _master_fernet.encrypt(raw_key_bytes).decode()


def _unwrap_user_key(wrapped: str) -> bytes:
    """Fernet-decrypt a stored wrapped user key."""
    return _master_fernet.decrypt(wrapped.encode())


def _aes_gcm_encrypt(plaintext: str, key_bytes: bytes) -> str:
    """AES-256-GCM encrypt. Returns uk1:-prefixed base64(nonce+ciphertext)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key_bytes)
    nonce = _secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    blob = base64.b64encode(nonce + ct).decode()
    return f"{_PER_USER_PREFIX}{blob}"


def _aes_gcm_decrypt(ciphertext: str, key_bytes: bytes) -> str:
    """AES-256-GCM decrypt a uk1:-prefixed base64 string."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    blob = base64.b64decode(ciphertext[len(_PER_USER_PREFIX):])
    nonce, ct = blob[:12], blob[12:]
    aesgcm = AESGCM(key_bytes)
    return aesgcm.decrypt(nonce, ct, None).decode()


def is_per_user_ciphertext(ciphertext: str) -> bool:
    """Return True if this ciphertext was produced by encrypt_for_user()."""
    return isinstance(ciphertext, str) and ciphertext.startswith(_PER_USER_PREFIX)


async def _get_or_create_user_key(mongo_db, user_id: str) -> bytes:
    """
    Return the 32-byte AES key for this user.
    Creates and persists a new random key if the user doesn't have one yet.
    """
    doc = await mongo_db[_USER_KEYS_COLLECTION].find_one({"user_id": user_id})
    if doc:
        return _unwrap_user_key(doc["wrapped_key"])

    raw_key = _secrets.token_bytes(32)
    wrapped = _wrap_user_key(raw_key)
    try:
        await mongo_db[_USER_KEYS_COLLECTION].insert_one({
            "user_id": user_id,
            "wrapped_key": wrapped,
        })
    except Exception:
        # Race condition: another request created it — re-fetch
        doc = await mongo_db[_USER_KEYS_COLLECTION].find_one({"user_id": user_id})
        if doc:
            return _unwrap_user_key(doc["wrapped_key"])
    return raw_key


async def encrypt_for_user(plaintext: str, user_id: str, mongo_db) -> str:
    """Encrypt plaintext with this user's unique key. Returns uk1:-prefixed ciphertext."""
    key = await _get_or_create_user_key(mongo_db, user_id)
    return _aes_gcm_encrypt(plaintext, key)


async def decrypt_for_user(ciphertext: str, user_id: str, mongo_db) -> str:
    """
    Decrypt a ciphertext for a user.
    Per-user ciphertext (uk1: prefix) → user's AES key.
    Legacy ciphertext (Fernet token) → global master key.
    """
    if is_per_user_ciphertext(ciphertext):
        key = await _get_or_create_user_key(mongo_db, user_id)
        return _aes_gcm_decrypt(ciphertext, key)
    return decrypt_api_key(ciphertext)


async def create_user_key_index(mongo_db) -> None:
    """Create unique index on user_keys.user_id — call once at startup."""
    await mongo_db[_USER_KEYS_COLLECTION].create_index("user_id", unique=True)