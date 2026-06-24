"""WeChat parser — best-effort, plaintext-export oriented (spec §10).

WeChat's on-disk DB is SQLCipher-encrypted and the decryption tooling is
fragile, so the supported path here is a **decrypted/plaintext export**:
``.txt`` (most common), ``.csv``, or ``.html`` saved by a local-decrypt helper.
Media / quoted-card payloads are stripped to a short tag.

If handed an **encrypted SQLite (SQLCipher) database**, we cannot decrypt it
inline → raise :class:`ParserNeedsManualExport` so the portal can show the
manual-export / plaintext-paste fallback.
"""
from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import List, Optional

from dateutil import parser as dateparser

from .base import NormalizedMessage, NormalizedTranscript, ParserNeedsManualExport

SQLITE_MAGIC = b"SQLite format 3\x00"

# Line shape reused from ex-skill's wechat regex:
#   "2021-03-12 21:04:33 小美: 你在干嘛"  (date  sender:  content)
# colon may be ASCII ":" or full-width "：".
_LINE = re.compile(
    r"^\s*(?P<date>\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?)"
    r"\s+(?P<sender>[^:：]{1,40})[:：]\s*(?P<content>.*)$"
)

# Media / system tags WeChat emits in text exports → normalize to a short tag.
_MEDIA_TAGS = re.compile(
    r"\[(?:图片|视频|语音|表情|动画表情|文件|位置|名片|链接|转账|红包|拍了拍|"
    r"撤回了一条消息|Photo|Video|Voice|Sticker|File|Location|Card|Link)\]"
)
_SYSTEM_LINE = re.compile(r"(以上是打招呼的内容|^-{3,}$|^==+$)")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self.parts.append(data.strip())


def _strip_media(content: str) -> str:
    # Remove media/system tags. A message that was ONLY a media tag becomes
    # empty and is dropped by the caller; inline text around a tag is kept.
    return _MEDIA_TAGS.sub("", content).strip()


def _check_not_encrypted_db(path: str) -> None:
    with open(path, "rb") as fh:
        head = fh.read(16)
    if head.startswith(SQLITE_MAGIC):
        # plain SQLite that happens to be a wechat dump — still unsupported here
        raise ParserNeedsManualExport(
            "WeChat SQLite database detected — export a plaintext .txt/.csv first."
        )
    # SQLCipher DBs have a random-looking 16-byte salt header (no magic). If the
    # file is binary-ish and named like a wechat db, treat as encrypted.
    if path.lower().endswith((".db", ".sqlite", ".sqlite3", ".dat")):
        raise ParserNeedsManualExport(
            "Encrypted WeChat database — provide a decrypted plaintext export."
        )


def _emit(
    out: NormalizedTranscript,
    sender: str,
    ts: datetime,
    content: str,
    target: Optional[str],
    owner_holder: List[Optional[str]],
) -> None:
    content = _strip_media(content)
    if not content:
        return
    sender = sender.strip()
    if target:
        direction = "in" if sender == target.strip() else "out"
    else:
        if owner_holder[0] is None:
            owner_holder[0] = sender
        direction = "out" if sender == owner_holder[0] else "in"
    out.append(NormalizedMessage(sender=sender, ts=ts, text=content, direction=direction))


def _parse_text(text: str, target: Optional[str]) -> NormalizedTranscript:
    out: NormalizedTranscript = []
    owner_holder: List[Optional[str]] = [None]
    last_idx: Optional[int] = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip() or _SYSTEM_LINE.search(line):
            continue
        m = _LINE.match(line)
        if not m:
            # continuation of the previous message body
            if last_idx is not None:
                out[last_idx].text = (out[last_idx].text + "\n" + line.strip()).strip()
            continue
        try:
            ts = dateparser.parse(m.group("date"))
        except (ValueError, OverflowError):
            continue
        before = len(out)
        _emit(out, m.group("sender"), ts, m.group("content"), target, owner_holder)
        last_idx = len(out) - 1 if len(out) > before else None
    return out


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    _check_not_encrypted_db(path)
    ext = os.path.splitext(path)[1].lower()

    if ext in (".html", ".htm"):
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            extractor = _TextExtractor()
            extractor.feed(fh.read())
        return _parse_text("\n".join(extractor.parts), target)

    if ext == ".csv":
        out: NormalizedTranscript = []
        owner_holder: List[Optional[str]] = [None]
        with open(path, "r", encoding="utf-8", errors="ignore", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                low = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
                content = low.get("content") or low.get("message") or low.get("body") or ""
                sender = low.get("sender") or low.get("talker") or low.get("nickname") or ""
                date_raw = low.get("time") or low.get("date") or low.get("createtime") or ""
                if not content or not sender:
                    continue
                try:
                    ts = dateparser.parse(date_raw)
                except (ValueError, OverflowError, TypeError):
                    continue
                _emit(out, sender, ts, content, target, owner_holder)
        return out

    # default: plaintext .txt
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return _parse_text(fh.read(), target)
