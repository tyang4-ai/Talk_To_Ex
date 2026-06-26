"""Auth API: register + login, both returning a signed JWT."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import User, get_session
from .deps import get_current_user
from .jwt import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str
    phone: Optional[str] = None  # register only — where the ex texts them first


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    subscription_status: str


def _token_response(user: User) -> TokenResponse:
    assert user.id is not None
    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        email=user.email,
        subscription_status=user.subscription_status,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(creds: Credentials, session: Session = Depends(get_session)) -> TokenResponse:
    email = creds.email.lower()
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    phone = (creds.phone or "").strip() or None
    user = User(email=email, pw_hash=hash_password(creds.password), phone_e164=phone)
    session.add(user)
    session.commit()
    session.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(creds: Credentials, session: Session = Depends(get_session)) -> TokenResponse:
    email = creds.email.lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None or not verify_password(creds.password, user.pw_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return _token_response(user)


@router.get("/me", response_model=TokenResponse)
def me(user: User = Depends(get_current_user)) -> TokenResponse:
    """Protected probe: 401s without a valid bearer token."""
    return _token_response(user)
