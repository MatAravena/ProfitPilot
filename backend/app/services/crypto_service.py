from __future__ import annotations
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.fernet import Fernet

from app.core.config import get_settings

_settings = get_settings()


def _fernet() -> Fernet:
    # Derive a 32-byte Fernet key from SECRET_KEY using its first 32 bytes (padded if needed)
    raw = _settings.SECRET_KEY.encode()
    key = (raw * 32)[:32]
    return Fernet(urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
