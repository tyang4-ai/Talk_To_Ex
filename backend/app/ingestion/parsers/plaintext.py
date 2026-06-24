"""Plaintext / PDF fallback parser — the always-works path (spec §10).

- ``.pdf`` → extract text with ``pdfminer.six`` (imported lazily so the package
  is optional at import time);
- otherwise read as UTF-8 text.

Line shape (reused from ex-skill's regex digesting):
``^<date> <sender>[:：] <content>``. Lines with no recognizable header are
treated as continuations of the previous message. If NO line matches the dated
header at all (a raw pasted blob), every non-empty line becomes one inbound
message so distillation still gets signal.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as dateparser

from .base import NormalizedMessage, NormalizedTranscript

# "2021-03-12 21:04  Alice: hey"  or  "3/12/2021, 9:04 PM - Alice: hey"
_LINE = re.compile(
    r"^\s*(?P<date>\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}"
    r"(?:[ T,]+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm])?)?)"
    r"\s*[-,]?\s*(?P<sender>[^:：]{1,40})[:：]\s*(?P<content>.*)$"
)


def _read_pdf(path: str) -> str:
    from pdfminer.high_level import extract_text  # lazy import

    return extract_text(path) or ""


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    if os.path.splitext(path)[1].lower() == ".pdf":
        raw = _read_pdf(path)
    else:
        raw = _read_text(path)

    out: NormalizedTranscript = []
    owner: Optional[str] = None
    matched_any = False
    last_idx: Optional[int] = None

    for raw_line in raw.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        m = _LINE.match(line)
        if not m:
            if last_idx is not None:
                out[last_idx].text = (out[last_idx].text + "\n" + line.strip()).strip()
            continue
        matched_any = True
        try:
            ts = dateparser.parse(m.group("date"))
        except (ValueError, OverflowError):
            ts = datetime.now(timezone.utc)
        sender = m.group("sender").strip()
        content = m.group("content").strip()
        if not content:
            last_idx = None
            continue
        if target:
            direction = "in" if sender == target.strip() else "out"
        else:
            if owner is None:
                owner = sender
            direction = "out" if sender == owner else "in"
        out.append(NormalizedMessage(sender=sender, ts=ts, text=content, direction=direction))
        last_idx = len(out) - 1

    if not matched_any:
        # raw pasted blob with no dated headers — keep every non-empty line as an
        # inbound message so the persona still has material to work with.
        now = datetime.now(timezone.utc)
        for raw_line in raw.splitlines():
            text = raw_line.strip()
            if not text:
                continue
            out.append(
                NormalizedMessage(sender=target or "ex", ts=now, text=text, direction="in")
            )

    return out
