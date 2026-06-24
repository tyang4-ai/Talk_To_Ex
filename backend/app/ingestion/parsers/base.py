"""Shared parser contracts. Every per-format parser emits the same
``NormalizedTranscript`` so the distillation pipeline is format-agnostic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Literal, Optional, Protocol, runtime_checkable

Direction = Literal["in", "out"]


@dataclass
class NormalizedMessage:
    """One message in a transcript.

    ``direction`` is from the *operator/owner's* perspective:
    - ``"out"`` = sent by the account owner (``is_from_me`` on iMessage),
    - ``"in"`` = received from the other party (the "ex" we model).
    """

    sender: str
    ts: datetime
    text: str
    direction: Direction


NormalizedTranscript = List[NormalizedMessage]


@runtime_checkable
class Parser(Protocol):
    """Structural type every parser module satisfies via its ``parse`` callable.

    ``target`` is the optional display name / handle of the ex, used by formats
    that need to disambiguate which participant is the modelled persona.
    """

    def parse(self, path: str, target: Optional[str] = None) -> NormalizedTranscript:
        ...


class ParserNeedsManualExport(Exception):
    """Raised when an input cannot be parsed automatically (e.g. an encrypted
    WeChat database) and the user must supply a decrypted/plaintext export
    instead. The portal surfaces this as a manual-paste fallback path."""
