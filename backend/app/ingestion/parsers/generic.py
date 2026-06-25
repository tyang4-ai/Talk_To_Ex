"""Generic structured-chat parser — the "anything" catch-all for CSV and JSON
exports that aren't one of the named platforms (spec §10).

This is the *last structured resort* before raw plaintext, so it is maximally
tolerant: per-record parsing is wrapped in try/except and bad rows are skipped
rather than thrown.

Handles BOTH:
- **CSV** (``csv.DictReader`` with a sniffed dialect). Columns are mapped
  case-insensitively by header name from candidate lists.
- **JSON**: a top-level list of objects, or ``{"messages": [...]}``. Each object
  is mapped with the same candidate lists. ``date`` may be an epoch int
  (seconds) or an ISO/string parsed with ``dateutil``.

Direction is from the account owner's view: ``"in"`` = a message from the ex
(the modelled persona), ``"out"`` = the owner's own message. With ``target``
given, ``"in"`` when the sender matches it (case-insensitive, trimmed). Without
``target``, the plaintext owner heuristic applies: the FIRST distinct sender is
the owner (``"out"``), everyone else ``"in"``.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as dateparser
from ftfy import fix_text

from .base import NormalizedMessage, NormalizedTranscript

# candidate header/key names, tried in order (case-insensitive)
_SENDER_KEYS = ("sender", "from", "author", "name", "who", "user", "speaker")
_TEXT_KEYS = ("message", "content", "text", "body", "msg")
_DATE_KEYS = ("date", "time", "timestamp", "datetime", "sent", "created")


def _fix(value: Optional[str]) -> str:
    if not value:
        return ""
    # repair UTF-8-as-latin1 mojibake; ftfy is a no-op on already-valid text
    # (a bare s.encode('latin-1').decode('utf-8') throws on clean text).
    return fix_text(str(value))


def _pick(row: dict, keys) -> str:
    """Return the first non-empty value among ``keys`` (case-insensitive)."""
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return ""


def _to_ts(value) -> datetime:
    """epoch int (seconds) → fromtimestamp; ISO/string → dateutil; else now()."""
    if value in (None, ""):
        return datetime.now(timezone.utc)
    # numeric epoch (int, float, or an all-digit string)
    if isinstance(value, bool):
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            secs = value / 1000.0 if value > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return datetime.now(timezone.utc)
    s = str(value).strip()
    if s.isdigit():
        try:
            num = int(s)
            secs = num / 1000.0 if num > 10_000_000_000 else float(num)
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return datetime.now(timezone.utc)
    try:
        ts = dateparser.parse(s)
    except (ValueError, OverflowError, TypeError):
        return datetime.now(timezone.utc)
    if ts is None:
        return datetime.now(timezone.utc)
    # normalise to a timezone-aware UTC datetime
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _lower_row(row: dict) -> dict:
    """Normalise a record's keys to trimmed lowercase for candidate lookup."""
    return {(k or "").strip().lower(): v for k, v in row.items()}


def _iter_records(path: str) -> List[dict]:
    """Yield raw record dicts from a CSV or JSON file. Be tolerant: an
    unreadable / unrecognised file yields nothing rather than throwing."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore", newline="") as fh:
            head = fh.read(4096)
    except OSError:
        return []

    stripped = head.lstrip()
    ext = os.path.splitext(path)[1].lower()
    looks_json = stripped.startswith("{") or stripped.startswith("[")

    # Prefer JSON when the content (or extension) looks like JSON.
    if ext == ".json" or looks_json:
        recs = _iter_json(path)
        if recs is not None:
            return recs
        # fall through to CSV if JSON didn't parse

    return _iter_csv(path)


def _iter_json(path: str) -> Optional[List[dict]]:
    try:
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8", "ignore"))
    except (ValueError, OSError):
        return None
    if isinstance(data, dict):
        items = data.get("messages")
        if items is None:
            # maybe a single record, or some other wrapper holding the list
            if any(any(k in data for k in group) for group in (_SENDER_KEYS, _TEXT_KEYS)):
                items = [data]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
    elif isinstance(data, list):
        items = data
    else:
        items = None
    if not isinstance(items, list):
        return None
    return [r for r in items if isinstance(r, dict)]


def _iter_csv(path: str) -> List[dict]:
    rows: List[dict] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(fh, dialect=dialect)
            for row in reader:
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    ex_name: Optional[str] = target.strip().lower() if target else None

    out: NormalizedTranscript = []
    owner: Optional[str] = None  # first distinct sender, for the no-target heuristic

    for record in _iter_records(path):
        try:
            row = _lower_row(record)
            text = _fix(_pick(row, _TEXT_KEYS)).strip()
            if not text:
                # skip empty/whitespace-only and non-message/service records
                continue
            sender = _fix(_pick(row, _SENDER_KEYS)).strip()
            ts = _to_ts(_pick(row, _DATE_KEYS) or None)

            if ex_name is not None:
                direction = "in" if sender.lower() == ex_name else "out"
            else:
                if owner is None:
                    owner = sender
                direction = "out" if sender == owner else "in"

            out.append(
                NormalizedMessage(sender=sender, ts=ts, text=text, direction=direction)
            )
        except Exception:
            # maximally tolerant: skip any record that fails to parse
            continue

    out.sort(key=lambda m: m.ts)
    return out
