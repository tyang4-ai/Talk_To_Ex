"""WhatsApp ``_chat.txt`` parser ("Export chat → Without media").

Implements the ``joweich/chat-miner`` regex set inline (no network dep):
- iOS    ``[DD/MM/YY, HH:MM:SS] Sender: body``  (also ``[YYYY/MM/DD, ...]``)
- Android ``M/D/YY, H:MM AM - Sender: body``    (12h or 24h)
Gotchas (spec §10):
- strip the U+200E (LTR mark) and BOM that WhatsApp injects;
- **merge continuation lines** (a body that wraps onto following lines that do
  NOT start with a timestamp belongs to the previous message);
- drop system lines and ``<Media omitted>`` / media-attached placeholders;
- tolerate Chinese locale ``上午/下午`` (AM/PM) markers.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple

from dateutil import parser as dateparser

from .base import NormalizedMessage, NormalizedTranscript

# Invisible marks WhatsApp sprinkles into the export.
_INVISIBLE = dict.fromkeys(
    [0x200E, 0x200F, 0xFEFF, 0x202A, 0x202B, 0x202C, 0x2066, 0x2067, 0x2068, 0x2069],
    None,
)

# iOS:  [12/03/2021, 21:04:33] Alice: hi
_IOS = re.compile(
    r"^\[(?P<date>[^\],]+),\s*(?P<time>[^\]]+)\]\s*"
    r"(?P<sender>[^:]+?):\s?(?P<body>.*)$",
    re.DOTALL,
)
# Android: 12/03/2021, 9:04 PM - Alice: hi  (24h "21:04 - "; zh "下午9:06 - ").
# The AM/PM or 上午/下午 marker may appear before OR after the digits.
_ANDROID = re.compile(
    r"^(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),\s*"
    r"(?P<time>(?:上午|下午)?\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm]|上午|下午)?)"
    r"\s*-\s*(?P<rest>.*)$",
    re.DOTALL,
)

# Lines that are system notices (no "Sender: body"), or media placeholders.
_MEDIA = re.compile(
    r"<\s*(?:media omitted|附件已省略|媒体文件已省略)\s*>|image omitted|video omitted|"
    r"audio omitted|sticker omitted|GIF omitted|document omitted|图片省略|视频省略",
    re.IGNORECASE,
)
_SYSTEM_HINTS = (
    "Messages and calls are end-to-end encrypted",
    "端到端加密",
    "created group",
    "added you",
    "changed the subject",
    "changed this group's icon",
    "changed their phone number",
    "你已加入",
    "更改了群组",
)


def _clean(line: str) -> str:
    return line.translate(_INVISIBLE)


_ZH_AMPM = re.compile(r"(上午|下午)")


def _norm_ampm(time_str: str) -> str:
    # Map Chinese 上午/下午 to AM/PM. The marker may lead the time ("下午9:06");
    # dateutil needs it trailing, so strip then append.
    marker = ""
    m = _ZH_AMPM.search(time_str)
    if m:
        marker = " AM" if m.group(1) == "上午" else " PM"
        time_str = _ZH_AMPM.sub("", time_str)
    return (time_str.strip() + marker).strip()


def _parse_ts(date_str: str, time_str: str) -> datetime:
    t = _norm_ampm(time_str)
    raw = f"{date_str.strip()} {t}"
    # WhatsApp is day-first outside the US; dateutil's dayfirst handles the
    # common DD/MM case while still parsing YYYY/MM/DD unambiguously.
    try:
        return dateparser.parse(raw, dayfirst=True)
    except (ValueError, OverflowError):
        return dateparser.parse(raw)


def _split_sender_body(rest: str) -> Optional[Tuple[str, str]]:
    """Android: after the timestamp the remainder is ``Sender: body`` or a
    system notice with no colon. Return None for system lines."""
    if ":" not in rest:
        return None
    sender, body = rest.split(":", 1)
    sender = sender.strip()
    if not sender or "\n" in sender:
        return None
    return sender, body.lstrip()


def _start_of_message(line: str) -> Optional[Tuple[str, str, str]]:
    """Return ``(date, time, sender:body-or-rest)`` tuple if the line begins a
    new message, else None (continuation line)."""
    m = _IOS.match(line)
    if m:
        return m.group("date"), m.group("time"), f"{m.group('sender')}:{m.group('body')}"
    m = _ANDROID.match(line)
    if m:
        return m.group("date"), m.group("time"), m.group("rest")
    return None


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        raw_lines = fh.read().splitlines()

    # Group physical lines into logical messages (merge continuation lines).
    grouped: List[Tuple[str, str, str]] = []  # (date, time, sender:body)
    for raw in raw_lines:
        line = _clean(raw)
        start = _start_of_message(line)
        if start is not None:
            grouped.append([start[0], start[1], start[2]])  # type: ignore[arg-type]
        elif grouped:
            # continuation of the previous message body
            grouped[-1][2] += "\n" + line  # type: ignore[index]
        # else: leading junk before the first timestamp → ignore

    out: NormalizedTranscript = []
    owner: Optional[str] = None
    ex_name: Optional[str] = target.strip() if target else None

    for date_str, time_str, payload in grouped:
        parsed = _split_sender_body(payload)
        if parsed is None:
            continue  # system notice
        sender, body = parsed

        if _MEDIA.search(body) or any(h in body for h in _SYSTEM_HINTS):
            continue
        body = body.strip()
        if not body:
            continue

        try:
            ts = _parse_ts(date_str, time_str)
        except (ValueError, OverflowError):
            continue

        # Identify the ex vs owner. First distinct sender that isn't the target
        # becomes the owner if no target was supplied.
        if ex_name is None and owner is None:
            owner = sender
        if ex_name is not None:
            direction = "in" if sender == ex_name else "out"
        else:
            direction = "out" if sender == owner else "in"

        out.append(
            NormalizedMessage(sender=sender, ts=ts, text=body, direction=direction)
        )

    return out
