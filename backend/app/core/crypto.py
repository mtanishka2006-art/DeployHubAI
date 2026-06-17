"""Symmetric encryption for connector credentials at rest (Fernet).

The key is derived deterministically from ``FERNET_KEY`` (or ``JWT_SECRET`` as a
fallback) so the platform encrypts/decrypts consistently with zero extra config.
``cryptography`` ships transitively via python-jose[cryptography], so this has no
new hard dependency, but we still degrade gracefully if it is ever missing.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict

from app.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken

    _AVAILABLE = True
except Exception:  # noqa: BLE001 - cryptography unavailable
    _AVAILABLE = False
    logger.warning("cryptography not available; credential encryption disabled")


def _fernet():
    secret = (settings.FERNET_KEY or settings.JWT_SECRET).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    if not _AVAILABLE:
        # Last-resort obfuscation only; cryptography should be present in prod.
        return "b64:" + base64.urlsafe_b64encode(plaintext.encode()).decode()
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if token.startswith("b64:"):
        return base64.urlsafe_b64decode(token[4:].encode()).decode()
    if not _AVAILABLE:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("failed to decrypt credentials (key changed?)")
        return ""


def encrypt_dict(data: Dict[str, Any]) -> str:
    return encrypt(json.dumps(data))


def decrypt_dict(token: str) -> Dict[str, Any]:
    raw = decrypt(token)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
