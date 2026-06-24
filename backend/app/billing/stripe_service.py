"""Stripe Checkout (subscription mode). The stripe SDK is injected so tests can
pass a fake; secrets are read at call time so import never needs real keys."""
from __future__ import annotations

from typing import Any

from ..config import require, settings
from ..db import User


def _default_client() -> Any:
    import stripe

    return stripe


def create_checkout(user: User, client: Any | None = None) -> str:
    """Create a subscription Checkout Session for `user` and return its URL.

    `client` defaults to the real `stripe` module. The secret key and price id
    are required only here, at the boundary call.
    """
    if client is None:
        client = _default_client()

    client.api_key = require("stripe_secret_key")
    price_id = require("stripe_price_id")
    base = settings.app_url.rstrip("/")

    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/?checkout=cancel",
        # Bind the session back to our user so the webhook can resolve them even
        # if Stripe hasn't populated customer/email yet.
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id)},
    }
    if user.stripe_customer_id:
        params["customer"] = user.stripe_customer_id
    elif user.email:
        params["customer_email"] = user.email

    session = client.checkout.Session.create(**params)
    # Stripe returns an object with `.url`; fakes may return a dict.
    url = getattr(session, "url", None)
    if url is None and isinstance(session, dict):
        url = session.get("url")
    if not url:
        raise RuntimeError("Stripe did not return a checkout URL")
    return url
