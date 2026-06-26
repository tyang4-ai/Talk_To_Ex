"""Telegram parser — Telegram Desktop "Export chat history" ``result.json``.

Verified gotchas:
- only ``type == "message"`` records carry a conversation turn; ``type ==
  "service"`` rows (``phone_call``, ``pin_message``, joins, ...) are skipped;
- the ``text`` field is polymorphic: either a plain string OR a list whose
  items are plain strings and/or ``{"type": ..., "text": ...}`` entity objects
  (bold/italic/link/mention/...). Concatenate every textual part in order;
- prefer ``date_unixtime`` (epoch seconds, as a string) for the timestamp; fall
  back to the ISO ``date`` field, then to "now";
- fix mojibake per text/name field with ``ftfy.fix_text`` (a no-op on already
  valid text);
- ``from`` is the sender display name; ``direction`` comes from matching it
  against ``target`` (case-insensitive, trimmed), else the first-sender owner
  heuristic;
- input is a single ``result.json`` file (or a directory / ``.zip`` containing
  one); the top-level object holds ``messages[]``.
"""
from __future__ import annotations

import glob
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as dateparser
from ftfy import fix_text

from .base import NormalizedMessage, NormalizedTranscript, reject_zip_bomb


def _fix(value: Optional[str]) -> str:
    if not value:
        return ""
    # ftfy repairs UTF-8-mangled-as-latin-1 mojibake and is a no-op on clean
    # text (a bare s.encode('latin-1').decode('utf-8') throws on valid text).
    return fix_text(value)


def _iter_export_files(path: str) -> List[str]:
    """Return the ``result.json`` file paths, extracting a zip to a temp dir if
    necessary. The temp dir is intentionally left for the OS to reap."""
    if os.path.isfile(path) and zipfile.is_zipfile(path):
        tmp = tempfile.mkdtemp(prefix="tg_export_")
        with zipfile.ZipFile(path) as zf:
            reject_zip_bomb(zf)
            zf.extractall(tmp)
        root = tmp
    elif os.path.isdir(path):
        root = path
    else:
        # a single result.json file
        return [path]

    files = glob.glob(os.path.join(root, "**", "result.json"), recursive=True)
    if not files:
        # fall back: any *.json anywhere under the export
        files = glob.glob(os.path.join(root, "**", "*.json"), recursive=True)
    return sorted(files)


def _text_of(value) -> str:
    """Flatten Telegram's polymorphic ``text`` into a single string.

    ``value`` is either a plain string, or a list whose items are plain strings
    and/or ``{"type", "text"}`` entity objects — concatenate the textual parts.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return ""


def _ts_of(m: dict) -> datetime:
    # prefer date_unixtime (epoch seconds, usually a string); fall back to the
    # ISO `date`, then to now — never throw.
    epoch = m.get("date_unixtime")
    if epoch is not None:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            pass
    iso = m.get("date")
    if iso:
        try:
            dt = dateparser.parse(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, OverflowError, TypeError):
            pass
    return datetime.now(timezone.utc)


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    raw: List[dict] = []
    for fp in _iter_export_files(path):
        try:
            with open(fp, "rb") as fh:
                obj = json.loads(fh.read().decode("utf-8", "ignore"))
        except (ValueError, OSError):
            continue
        if not isinstance(obj, dict):
            continue
        for m in obj.get("messages") or []:
            if isinstance(m, dict):
                raw.append(m)

    ex_name: Optional[str] = target.strip().lower() if target else None
    owner: Optional[str] = None

    out: NormalizedTranscript = []
    for m in raw:
        try:
            if m.get("type") != "message":
                # skip service / non-message records (phone_call, joins, ...)
                continue
            sender = _fix(m.get("from") or "")
            text = _fix(_text_of(m.get("text"))).strip()
            if not text:
                # skip media-only / empty records with no textual body
                continue
            ts = _ts_of(m)

            # direction is from the owner's view: "in" = from the ex.
            if ex_name is not None:
                direction = "in" if sender.strip().lower() == ex_name else "out"
            else:
                # first distinct sender seen is the owner ("out"); else "in".
                if owner is None:
                    owner = sender
                direction = "out" if sender == owner else "in"

            out.append(
                NormalizedMessage(sender=sender, ts=ts, text=text, direction=direction)
            )
        except Exception:
            # be tolerant: skip any malformed record rather than throwing.
            continue

    out.sort(key=lambda msg: msg.ts)
    return out
