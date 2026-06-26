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


def reject_zip_bomb(
    zf,
    *,
    max_members: int = 20000,
    max_total_bytes: int = 300 * 1024 * 1024,
    max_ratio: int = 120,
) -> None:
    """Guard a ``zipfile.ZipFile`` against decompression bombs BEFORE extracting.

    The 50 MB upload cap bounds the raw archive, not its expansion — a tiny zip
    can balloon to GBs and fill the disk / OOM the box. Reject archives with too
    many members, too much total uncompressed size, or an implausible compression
    ratio. Call this immediately before ``extractall``.
    """
    infos = zf.infolist()
    if len(infos) > max_members:
        raise ValueError("archive has too many files")
    total = sum(getattr(i, "file_size", 0) for i in infos)
    if total > max_total_bytes:
        raise ValueError("archive expands too large")
    comp = sum(getattr(i, "compress_size", 0) for i in infos) or 1
    if total / comp > max_ratio:
        raise ValueError("suspicious compression ratio (possible zip bomb)")
