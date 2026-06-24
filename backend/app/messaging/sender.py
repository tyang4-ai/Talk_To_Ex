"""Outbound SMS sender (spec §8, §9).

A reply is split into 1–3 short "bubbles"; each is sent as a SEPARATE Twilio
``Messages.create`` call with a randomized 1–3 s human-feeling delay between
them. The Twilio client and the sleeper are injected so tests run with zero
network and zero real wall-clock; the real client is built lazily from settings
(never at import) mirroring ``billing.number_service._default_twilio``.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Optional, Sequence

from ..config import require


def _default_twilio() -> Any:
    """Build the real Twilio REST client lazily (keys required only here)."""
    from twilio.rest import Client

    return Client(require("twilio_account_sid"), require("twilio_auth_token"))


class Sender:
    """Sends multi-bubble SMS replies via Twilio REST.

    Inject ``twilio`` (any object exposing ``messages.create(...)``) and
    ``sleeper`` (a ``float -> None`` callable) in tests; both default to the real
    client / ``time.sleep`` in production.
    """

    def send_bubbles(
        self,
        to: str,
        from_: str,
        bubbles: Sequence[str],
        twilio: Optional[Any] = None,
        sleeper: Optional[Callable[[float], None]] = None,
    ) -> list[Any]:
        """Send each bubble as its own message with a 1–3 s delay between them.

        The delay is applied BEFORE every bubble after the first, so the first
        bubble goes out immediately. Returns the list of Twilio message results
        (whatever ``messages.create`` returned), useful for assertions/logging.
        """
        client = twilio if twilio is not None else _default_twilio()
        sleep = sleeper if sleeper is not None else time.sleep

        results: list[Any] = []
        for i, bubble in enumerate(bubbles):
            if not bubble:
                continue
            if i > 0:
                sleep(random.uniform(1.0, 3.0))
            results.append(
                client.messages.create(to=to, from_=from_, body=bubble)
            )
        return results
