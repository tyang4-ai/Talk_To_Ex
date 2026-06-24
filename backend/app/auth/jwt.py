"""JWT encode/decode (PyJWT, HS256, settings.jwt_secret) + password hashing
(direct bcrypt — passlib is unmaintained and breaks on bcrypt 5). Secrets are
read at call time via require(), never at import, so the app imports cleanly
without a real JWT_SECRET."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt as pyjwt

from ..config import require

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(days=30)

# bcrypt only inspects the first 72 bytes of the password; truncate to match
# (bcrypt 5 raises instead of silently truncating).
_BCRYPT_MAX = 72


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the password."""
    digest = bcrypt.hashpw(password.encode("utf-8")[:_BCRYPT_MAX], bcrypt.gensalt())
    return digest.decode("ascii")


def verify_password(password: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:_BCRYPT_MAX], pw_hash.encode("ascii")
        )
    except (ValueError, TypeError):
        # Malformed/unknown hash — treat as a failed verification, not a crash.
        return False


def create_access_token(sub: str, *, extra: dict | None = None) -> str:
    """Sign a token whose subject is the user id (as a string, per JWT spec)."""
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int((now + TOKEN_TTL).timestamp()),
    }
    if extra:
        payload.update(extra)
    secret = require("jwt_secret")
    return pyjwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + verify a token. Raises pyjwt.PyJWTError subclasses on failure."""
    secret = require("jwt_secret")
    return pyjwt.decode(token, secret, algorithms=[ALGORITHM])
