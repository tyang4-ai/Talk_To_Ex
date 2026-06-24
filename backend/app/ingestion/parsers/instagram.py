"""Instagram DM parser — "Download Your Information" JSON export.

Verified gotchas (spec §10):
- glob ``**/messages/inbox/*/message_*.json`` and concat every ``messages[]``;
- **sort ascending by ``timestamp_ms``** (the export is newest-first + paginated
  across ``message_1.json``, ``message_2.json`` ...);
- fix mojibake per text field with ``ftfy.fix_text`` (NOT a bare
  ``latin-1``/``utf-8`` re-decode, which throws on already-valid text);
- support old (``sender`` / ``text``) and new (``sender_name`` / ``content``)
  key schemas;
- input may be a ``.zip``, a directory, or a single ``message_*.json`` file.
"""
from __future__ import annotations

import glob
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from ftfy import fix_text

from .base import NormalizedMessage, NormalizedTranscript


def _fix(value: Optional[str]) -> str:
    if not value:
        return ""
    # IG mangles UTF-8 as latin-1 escapes; ftfy repairs it and is a no-op on
    # already-valid text (the bare s.encode('latin-1').decode('utf-8') throws).
    return fix_text(value)


def _iter_message_files(path: str) -> List[str]:
    """Return the message JSON file paths, extracting a zip to a temp dir if
    necessary. The temp dir is intentionally left for the OS to reap; callers
    pass a real on-disk path."""
    if os.path.isfile(path) and zipfile.is_zipfile(path):
        tmp = tempfile.mkdtemp(prefix="ig_export_")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        root = tmp
    elif os.path.isdir(path):
        root = path
    else:
        # a single message_*.json file
        return [path]

    files = glob.glob(
        os.path.join(root, "**", "messages", "inbox", "*", "message_*.json"),
        recursive=True,
    )
    if not files:
        # fall back: any message_*.json anywhere under the export
        files = glob.glob(os.path.join(root, "**", "message_*.json"), recursive=True)
    return sorted(files)


def _participants(obj: dict) -> List[str]:
    names = []
    for p in obj.get("participants") or []:
        if isinstance(p, dict) and p.get("name"):
            names.append(_fix(p["name"]))
    return names


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    raw: List[dict] = []
    owner_name: Optional[str] = None
    ex_name: Optional[str] = _fix(target) if target else None

    for fp in _iter_message_files(path):
        try:
            with open(fp, "rb") as fh:
                obj = json.loads(fh.read().decode("utf-8", "ignore"))
        except (ValueError, OSError):
            continue
        if not isinstance(obj, dict):
            continue

        # Infer the ex (the non-owner participant). Meta's export lists the
        # owner last in `participants`; with exactly two we treat the other as
        # the ex when target wasn't given.
        parts = _participants(obj)
        if len(parts) == 2 and ex_name is None:
            ex_name = parts[0]

        for m in obj.get("messages") or []:
            if not isinstance(m, dict):
                continue
            raw.append(m)

    # sort ascending by timestamp_ms (export is newest-first + paginated)
    raw.sort(key=lambda m: m.get("timestamp_ms") or m.get("timestamp", 0))

    out: NormalizedTranscript = []
    for m in raw:
        sender = _fix(m.get("sender_name") or m.get("sender") or "")
        text = _fix(m.get("content") or m.get("text") or "")
        if not text:
            # skip media-only / unsend / reaction-only records with no body
            continue
        ts_ms = m.get("timestamp_ms")
        if ts_ms is None:
            ts_s = m.get("timestamp")
            ts = (
                datetime.fromtimestamp(ts_s, tz=timezone.utc)
                if ts_s is not None
                else datetime.now(timezone.utc)
            )
        else:
            ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

        # direction: messages from the ex are "in"; everything else "out".
        if ex_name is not None:
            direction = "in" if sender == ex_name else "out"
        else:
            # heuristic when we can't identify the ex: the owner is whoever sends
            # the most distinct-from-first... unknowable here, default "in".
            direction = "in"

        out.append(
            NormalizedMessage(sender=sender, ts=ts, text=text, direction=direction)
        )

    return out
