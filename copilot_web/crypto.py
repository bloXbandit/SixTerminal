"""
crypto.py — Encryption at rest for sensitive project files.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
Key is loaded from the ENCRYPTION_KEY environment variable.

If ENCRYPTION_KEY is not set, all operations are pass-through (no encryption).
This allows local development without a key while production is fully encrypted.

Usage:
    from crypto import encrypt_bytes, decrypt_bytes, encrypt_json, decrypt_json, encrypt_file, decrypt_file

Key generation (run once, store result in Render env vars):
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------

_fernet = None
_encryption_enabled = False

def _load_key():
    global _fernet, _encryption_enabled
    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not key:
        logger.info("[crypto] ENCRYPTION_KEY not set — encryption disabled (pass-through mode)")
        return
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        _encryption_enabled = True
        logger.info("[crypto] Encryption at rest enabled (Fernet/AES-128-CBC)")
    except Exception as e:
        logger.warning(f"[crypto] Failed to initialize encryption key: {e} — running in pass-through mode")

_load_key()


# ---------------------------------------------------------------------------
# Core byte-level operations
# ---------------------------------------------------------------------------

def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw bytes. Returns ciphertext bytes, or original bytes if encryption disabled."""
    if not _encryption_enabled or _fernet is None:
        return data
    return _fernet.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt raw bytes. Returns plaintext bytes, or original bytes if encryption disabled.
    Falls back to returning original bytes if decryption fails (handles unencrypted legacy files).
    """
    if not _encryption_enabled or _fernet is None:
        return data
    try:
        return _fernet.decrypt(data)
    except Exception:
        # File may be unencrypted (legacy) — return as-is
        logger.debug("[crypto] decrypt_bytes: token invalid, returning raw bytes (legacy file)")
        return data


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def encrypt_json(obj) -> bytes:
    """Serialize obj to JSON and encrypt. Returns encrypted bytes."""
    raw = json.dumps(obj, indent=2, default=str).encode("utf-8")
    return encrypt_bytes(raw)


def decrypt_json(data: bytes):
    """Decrypt bytes and deserialize JSON. Returns Python object."""
    raw = decrypt_bytes(data)
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------

def write_encrypted_json(path: str, obj) -> None:
    """Write a Python object as encrypted JSON to a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "wb") as f:
        f.write(encrypt_json(obj))


def read_encrypted_json(path: str):
    """Read and decrypt a JSON file. Returns Python object."""
    with open(path, "rb") as f:
        return decrypt_json(f.read())


def write_encrypted_bytes(path: str, data: bytes) -> None:
    """Write raw bytes to a file, encrypted."""
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "wb") as f:
        f.write(encrypt_bytes(data))


def read_encrypted_bytes(path: str) -> bytes:
    """Read and decrypt raw bytes from a file."""
    with open(path, "rb") as f:
        return decrypt_bytes(f.read())


def is_enabled() -> bool:
    """Returns True if encryption is active."""
    return _encryption_enabled
