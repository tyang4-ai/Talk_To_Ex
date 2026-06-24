"""iMessage / SMS parser — reads an iPhone backup's ``sms.db`` as plain SQLite.

Verified gotchas (spec §10):
- join ``message`` / ``handle`` / ``chat`` / ``chat_message_join``;
- ``message.text`` is NULL on iOS 16+ → decode ``attributedBody`` (an
  NSAttributedString typedstream) with ``pytypedstream`` (NEVER naive byte
  slicing — it corrupts CJK);
- ``message.date`` is nanoseconds (iOS 16+) OR seconds since the Apple epoch
  (2001-01-01). **Branch per-row by magnitude**, then add ``978307200`` to map
  to the Unix epoch;
- ``is_from_me`` → direction (``1`` = "out", ``0`` = "in" = the ex's voice).

The ``attributedBody`` decoder is injected (``decode_attributed_body``) so tests
can exercise the NULL-text fallback without the optional native dependency.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, List, Optional

from .base import NormalizedMessage, NormalizedTranscript

APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01
# Anything bigger than this is nanoseconds, not seconds, since the Apple epoch.
# ~1e9 seconds since 2001 reaches the year ~2033; real ns values are ~1e18.
_NS_THRESHOLD = 1_000_000_000_000  # 1e12

_QUERY = """
SELECT
    m.ROWID            AS rowid,
    m.text             AS text,
    m.attributedBody   AS attributed_body,
    m.date             AS date,
    m.is_from_me       AS is_from_me,
    h.id               AS handle_id
FROM message m
LEFT JOIN handle h           ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
LEFT JOIN chat c             ON c.ROWID = cmj.chat_id
ORDER BY m.date ASC
"""


def apple_date_to_datetime(value: int) -> datetime:
    """Map an iMessage ``date`` (ns or s since 2001-01-01) to an aware UTC
    datetime, branching per row by magnitude (iOS 16+ mixes the two)."""
    if value >= _NS_THRESHOLD:
        seconds = value / 1_000_000_000.0
    else:
        seconds = float(value)
    return datetime.fromtimestamp(seconds + APPLE_EPOCH_OFFSET, tz=timezone.utc)


def _default_decode_attributed_body(blob: Optional[bytes]) -> str:
    """Decode an NSAttributedString typedstream blob to its plain string.

    Uses ``pytypedstream`` (imported lazily so the package is optional and the
    module imports without it). Returns ``""`` on any failure rather than
    raising, so one bad row never aborts a whole import."""
    if not blob:
        return ""
    try:
        import typedstream  # provided by the `pytypedstream` distribution
    except ImportError:
        return ""
    try:
        ts = typedstream.unarchive_from_data(blob)
    except Exception:  # noqa: BLE001 - corrupt/foreign blob, skip gracefully
        return ""
    # The unarchived object contains the string; pytypedstream exposes the
    # NSString contents as a `contents`/`value` sequence. Walk it defensively.
    for attr in ("contents", "value", "string"):
        val = getattr(ts, attr, None)
        if isinstance(val, str) and val:
            return val
    # Fallback: scan the unarchived elements for the first non-empty str.
    try:
        for element in ts:  # type: ignore[union-attr]
            if isinstance(element, str) and element:
                return element
    except TypeError:
        pass
    return ""


def parse(
    path: str,
    target: Optional[str] = None,
    *,
    decode_attributed_body: Callable[[Optional[bytes]], str] = _default_decode_attributed_body,
) -> NormalizedTranscript:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(_QUERY).fetchall()
    finally:
        conn.close()

    out: NormalizedTranscript = []
    seen_rowids: set[int] = set()
    for row in rows:
        # chat_message_join can fan a message into multiple rows; de-dupe.
        rowid = row["rowid"]
        if rowid in seen_rowids:
            continue
        seen_rowids.add(rowid)

        text = row["text"]
        if text is None or text == "":
            text = decode_attributed_body(row["attributed_body"])
        if not text:
            continue

        date_val = row["date"]
        if date_val is None:
            continue
        ts = apple_date_to_datetime(int(date_val))

        is_from_me = bool(row["is_from_me"])
        direction = "out" if is_from_me else "in"
        sender = "me" if is_from_me else (row["handle_id"] or target or "ex")

        out.append(
            NormalizedMessage(sender=sender, ts=ts, text=text, direction=direction)
        )

    # SQL ORDER BY m.date is unreliable here: iOS 16+ mixes ns and s magnitudes
    # in the same column, so sort by the *converted* timestamp instead.
    out.sort(key=lambda m: m.ts)
    return out
