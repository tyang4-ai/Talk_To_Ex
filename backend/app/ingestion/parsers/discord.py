"""Discord DM parser — DiscordChatExporter JSON (and a CSV fallback).

DiscordChatExporter (https://github.com/Tyrrrz/DiscordChatExporter) is the tool
people use to dump a full DM, both sides. The JSON shape is::

    {
      "channel": {"type": "DirectTextChat", "name": "alice"},
      "messages": [
        {"id": "1", "type": "Default",
         "timestamp": "2023-05-01T12:00:00.000+00:00",
         "author": {"id": "42", "name": "alice", "nickname": "Alice"},
         "content": "hey, you up?"},
        ...
      ]
    }

Verified gotchas:
- sender display = ``nickname`` or ``name`` (nickname is the per-guild override);
- ``timestamp`` is ISO8601 with offset → parse with ``dateutil`` and coerce to UTC;
- keep only ``type`` in {"Default", "Reply"} — drop joins/pins/calls/etc.;
- skip empty/whitespace-only ``content`` (attachment- or embed-only messages);
- the file may be a ``.zip``, a directory of exports, or a single ``.json``/``.csv``;
- a bare top-level ``list`` of message objects is also accepted;
- repair mojibake on text and names with ``ftfy.fix_text`` (no-op on clean text).
"""
from __future__ import annotations

import csv
import glob
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from dateutil import parser as dateparser
from ftfy import fix_text

from .base import NormalizedMessage, NormalizedTranscript

# DiscordChatExporter emits these message kinds; only real chat lines carry a body
# worth modelling. Everything else (RecipientAdd, Call, ChannelPinnedMessage, ...)
# is a service record we drop.
_KEPT_TYPES = {"default", "reply"}


def _fix(value: Optional[str]) -> str:
    if not value:
        return ""
    # Discord exports are valid UTF-8, but pasted/re-encoded files can carry
    # mojibake; ftfy repairs it and is a no-op on already-clean text.
    return fix_text(value)


def _parse_ts(value: Optional[str]) -> datetime:
    if value:
        try:
            ts = dateparser.parse(value)
            if ts is not None:
                # ISO strings carry an offset; coerce to UTC (naive → assume UTC).
                if ts.tzinfo is None:
                    return ts.replace(tzinfo=timezone.utc)
                return ts.astimezone(timezone.utc)
        except (ValueError, OverflowError, TypeError):
            pass
    return datetime.now(timezone.utc)


def _iter_export_files(path: str) -> List[str]:
    """Return the export file paths (JSON/CSV), extracting a zip to a temp dir if
    necessary. A single non-zip file is returned as-is; the temp dir is left for
    the OS to reap."""
    if os.path.isfile(path) and zipfile.is_zipfile(path):
        tmp = tempfile.mkdtemp(prefix="discord_export_")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        root = tmp
    elif os.path.isdir(path):
        root = path
    else:
        return [path]

    files = glob.glob(os.path.join(root, "**", "*.json"), recursive=True)
    files += glob.glob(os.path.join(root, "**", "*.csv"), recursive=True)
    return sorted(files)


def _author_names(author: dict) -> List[str]:
    """The name + nickname a target string may match against (case-insensitive)."""
    names = []
    for key in ("name", "nickname"):
        v = author.get(key)
        if v:
            names.append(_fix(v).strip().lower())
    return names


def _direction(author: dict, target_norm: Optional[str], owner_key: Optional[str]):
    """direction + the owner-key chosen this row (for the heuristic path).

    With a ``target`` the ex is whoever's name/nickname matches it → "in".
    Without one, mirror plaintext.py: the FIRST distinct sender is the owner
    ("out"), everyone else "in". We key the owner by author id when present so
    a later display-name change can't confuse the heuristic.
    """
    if target_norm is not None:
        is_ex = target_norm in _author_names(author)
        return ("in" if is_ex else "out"), owner_key
    key = str(author.get("id") or (_author_names(author) or [""])[0])
    if owner_key is None:
        owner_key = key
    return ("out" if key == owner_key else "in"), owner_key


def _rows_from_json(obj) -> List[dict]:
    if isinstance(obj, dict):
        msgs = obj.get("messages")
        return [m for m in msgs if isinstance(m, dict)] if isinstance(msgs, list) else []
    if isinstance(obj, list):
        return [m for m in obj if isinstance(m, dict)]
    return []


def _parse_json_file(fp: str) -> List[dict]:
    try:
        with open(fp, "rb") as fh:
            obj = json.loads(fh.read().decode("utf-8", "ignore"))
    except (ValueError, OSError):
        return []
    return _rows_from_json(obj)


def _parse_csv_file(fp: str) -> List[dict]:
    """DiscordChatExporter CSV: columns AuthorID, Author, Date, Content (+ others).
    Normalize each row into the same dict shape the JSON path produces."""
    rows: List[dict] = []
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append(
                        {
                            "type": "Default",
                            "timestamp": r.get("Date"),
                            "author": {
                                "id": r.get("AuthorID"),
                                "name": r.get("Author"),
                            },
                            "content": r.get("Content"),
                        }
                    )
                except Exception:
                    continue
    except OSError:
        return []
    return rows


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    target_norm = _fix(target).strip().lower() if target else None

    raw: List[dict] = []
    for fp in _iter_export_files(path):
        ext = os.path.splitext(fp)[1].lower()
        try:
            if ext == ".csv":
                raw.extend(_parse_csv_file(fp))
            else:
                raw.extend(_parse_json_file(fp))
        except Exception:
            # be tolerant: a single corrupt file never sinks the whole import
            continue

    out: NormalizedTranscript = []
    owner_key: Optional[str] = None
    for m in raw:
        try:
            mtype = str(m.get("type") or "Default").strip().lower()
            if mtype not in _KEPT_TYPES:
                continue
            text = _fix(m.get("content"))
            if not text.strip():
                # attachment-/embed-only or unsupported record with no body
                continue
            author = m.get("author") if isinstance(m.get("author"), dict) else {}
            sender = _fix(author.get("nickname") or author.get("name") or "")
            ts = _parse_ts(m.get("timestamp"))
            direction, owner_key = _direction(author, target_norm, owner_key)
            out.append(
                NormalizedMessage(sender=sender, ts=ts, text=text, direction=direction)
            )
        except Exception:
            # skip bad records rather than throwing
            continue

    out.sort(key=lambda msg: msg.ts)
    return out
