"""Android "SMS Backup & Restore" parser — XML (primary) + CSV (fallback).

XML schema: ``<smses><sms address="..." body="..." date="<ms>" type="1|2"/></smses>``
where ``type=1`` is **received** (``in``) and ``type=2`` is **sent** (``out``).
``date`` is Unix epoch **milliseconds**.

CSV fallback: a flat export with ``address``/``body``/``date``/``type`` columns
(or ``direction`` text), comma-delimited with a header row.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

from .base import NormalizedMessage, NormalizedTranscript


def _ts_from_ms(value: str) -> datetime:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    # date is epoch ms; some exports already store seconds — branch by magnitude.
    seconds = ms / 1000.0 if ms > 10_000_000_000 else float(ms)
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _direction_from_type(type_val: Optional[str]) -> str:
    # 1=received(in), 2=sent(out); MMS uses msg_box with same convention.
    return "out" if str(type_val).strip() == "2" else "in"


def _parse_xml(path: str, target: Optional[str]) -> NormalizedTranscript:
    out: NormalizedTranscript = []
    for _event, elem in ET.iterparse(path, events=("end",)):
        tag = elem.tag.lower()
        if tag not in ("sms", "mms"):
            continue
        body = elem.get("body")
        address = elem.get("address") or (target or "ex")
        if tag == "mms" and not body:
            # MMS bodies live in <part text="..."> children
            for part in elem.iter():
                if part.tag.lower() == "part" and part.get("text"):
                    body = part.get("text")
                    break
        if not body:
            elem.clear()
            continue
        type_val = elem.get("type") or elem.get("msg_box")
        direction = _direction_from_type(type_val)
        ts = _ts_from_ms(elem.get("date") or "0")
        sender = "me" if direction == "out" else address
        out.append(
            NormalizedMessage(sender=sender, ts=ts, text=body, direction=direction)
        )
        elem.clear()
    return out


def _parse_csv(path: str, target: Optional[str]) -> NormalizedTranscript:
    out: NormalizedTranscript = []
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            lower = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
            body = lower.get("body") or lower.get("text") or lower.get("message")
            if not body:
                continue
            address = lower.get("address") or lower.get("number") or (target or "ex")
            if "type" in lower and lower["type"]:
                direction = _direction_from_type(lower["type"])
            else:
                d = lower.get("direction", "").strip().lower()
                direction = "out" if d in ("out", "sent", "2") else "in"
            date_raw = lower.get("date") or lower.get("timestamp") or "0"
            ts = _ts_from_ms(date_raw)
            sender = "me" if direction == "out" else address
            out.append(
                NormalizedMessage(sender=sender, ts=ts, text=body.strip(), direction=direction)
            )
    return out


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    if os.path.splitext(path)[1].lower() == ".csv":
        return _parse_csv(path, target)
    # sniff: CSV files sometimes have no extension
    with open(path, "rb") as fh:
        head = fh.read(256).lstrip()
    if not head.startswith(b"<"):
        return _parse_csv(path, target)
    return _parse_xml(path, target)
