"""Fernet helpers for encrypting sensitive data at rest (chat logs, persona,
memories, style overlays)."""
from cryptography.fernet import Fernet

from .config import settings


def _fernet() -> Fernet:
    if not settings.fernet_key:
        raise RuntimeError("FERNET_KEY not set — generate one with Fernet.generate_key()")
    return Fernet(settings.fernet_key.encode())


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def enc_str(s: str) -> str:
    return encrypt(s.encode("utf-8")).decode("ascii")


def dec_str(token: str) -> str:
    return decrypt(token.encode("ascii")).decode("utf-8")
