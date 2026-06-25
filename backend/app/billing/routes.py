"""Billing API: start a Stripe Checkout session for the authenticated user."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth.deps import get_current_user
from ..config import settings
from ..db import User
from . import stripe_service

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutResponse(BaseModel):
    url: str


@router.post("/checkout", response_model=CheckoutResponse)
def checkout(user: User = Depends(get_current_user)) -> CheckoutResponse:
    # Billing off (demo, or free-for-all): skip Stripe entirely — send the user
    # straight into the wizard.
    if settings.demo_mode or not settings.require_subscription:
        return CheckoutResponse(url="/intake")
    try:
        url = stripe_service.create_checkout(user)
    except RuntimeError as exc:
        # Missing secret at the boundary, or Stripe returned no URL.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    return CheckoutResponse(url=url)
