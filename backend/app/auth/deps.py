"""Auth dependencies: extract+verify the bearer JWT, load the User from the DB."""
from __future__ import annotations

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from ..db import User, get_session
from .jwt import decode_token

# auto_error=False → we raise 401 ourselves for a missing header, so an
# unauthenticated request to a protected route consistently 401s (not 403).
_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_EXC
    try:
        payload = decode_token(creds.credentials)
    except pyjwt.PyJWTError:
        raise _CREDENTIALS_EXC
    sub = payload.get("sub")
    if sub is None:
        raise _CREDENTIALS_EXC
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise _CREDENTIALS_EXC
    user = session.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    return user
