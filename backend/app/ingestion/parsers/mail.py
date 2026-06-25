"""Email parser — Gmail Takeout / Thunderbird ``.mbox`` and single ``.eml``.

Named ``mail`` (NOT ``email``) so it never shadows the stdlib ``email`` package.

- ``.mbox`` → ``mailbox.mbox`` (one message per ``From `` separator line);
- ``.eml`` / ``.msg`` → ``email.message_from_binary_file`` for the lone message;
- fallback by content sniff: a real mbox starts a line with ``"From "`` (the
  mbox separator); an eml has RFC822 headers (``From:`` / ``Subject:`` / ``Date:``).

Per message (spec §10):
- ``From`` → ``email.utils.parseaddr`` → sender = display name or bare address;
- ``Date`` → ``email.utils.parsedate_to_datetime`` made tz-aware UTC (naive → UTC),
  falling back to ``datetime.now(timezone.utc)``;
- body = the FIRST ``text/plain`` part (decoded with its charset, ``errors="replace"``);
  if none, the FIRST ``text/html`` part with tags stripped. Quoted-reply lines
  (``>`` prefixed) and a trailing signature after a lone ``"-- "`` are dropped;
- fix mojibake on text and names with ``ftfy.fix_text`` (a no-op on clean text);
- skip messages whose body is empty / whitespace-only after cleaning;
- output sorted ascending by ``ts``.

direction is from the account OWNER's view: ``"in"`` = from the ex we model,
``"out"`` = the owner. ``target`` may be an email OR a name and is matched against
BOTH the From display name and the From address (case-insensitive; substring ok
for the address). With no target, the plaintext owner heuristic applies: the
FIRST distinct sender is the owner (``"out"``), everyone else ``"in"``.
"""
from __future__ import annotations

import email
import os
import re
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ftfy import fix_text

from .base import NormalizedMessage, NormalizedTranscript

_TAG = re.compile(r"<[^>]+>")
_MBOX_FROM = re.compile(rb"^From .*\d{4}", re.MULTILINE)


def _fix(value: Optional[str]) -> str:
    if not value:
        return ""
    # mail clients mangle UTF-8 as latin-1 escapes; ftfy repairs it and is a
    # no-op on already-valid text (a bare latin-1/utf-8 re-decode would throw).
    return fix_text(value)


def _strip_html(html: str) -> str:
    # drop scripts/styles wholesale, then strip the remaining tags.
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    # block-level tags become line breaks so structure survives; others vanish.
    html = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr)\s*/?>", "\n", html)
    text = _TAG.sub(" ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    # collapse runs of spaces/tabs introduced by tag removal, keep newlines.
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines())


def _part_text(part: Message) -> str:
    """Decode a single MIME part to ``str`` using its declared charset."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")


def _extract_body(msg: Message) -> str:
    """First ``text/plain`` part; else first ``text/html`` stripped of tags."""
    plain: Optional[str] = None
    html: Optional[str] = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain" and plain is None:
                plain = _part_text(part)
            elif ctype == "text/html" and html is None:
                html = _part_text(part)
    else:
        if msg.get_content_type() == "text/html":
            html = _part_text(msg)
        else:
            plain = _part_text(msg)

    if plain is not None and plain.strip():
        return plain
    if html is not None and html.strip():
        return _strip_html(html)
    return ""


def _clean_body(body: str) -> str:
    """Drop quoted-reply (``>``) lines and a trailing ``"-- "`` signature."""
    lines = body.splitlines()
    kept: List[str] = []
    for line in lines:
        if line.rstrip("\r") == "-- ":
            # everything after the signature delimiter is the signature block
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line.rstrip("\r"))
    return "\n".join(kept).strip()


def _ts_of(msg: Message) -> datetime:
    raw = msg.get("Date")
    try:
        dt = parsedate_to_datetime(raw) if raw else None
        if dt is None:
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(timezone.utc)


def _sender_of(msg: Message) -> Tuple[str, str]:
    """Return ``(display_or_addr, addr)`` from the ``From`` header."""
    name, addr = parseaddr(msg.get("From") or "")
    name = _fix(name).strip()
    addr = (addr or "").strip()
    sender = name or addr
    return sender, addr


def _matches_target(name: str, addr: str, target: str) -> bool:
    t = target.strip().lower()
    if not t:
        return False
    name_l = name.strip().lower()
    addr_l = addr.strip().lower()
    if t == name_l or t == addr_l:
        return True
    # email-shaped target → substring match against the address
    if "@" in t and t in addr_l:
        return True
    # name target → substring match against the display name
    return bool(name_l) and t in name_l


def _iter_messages(path: str) -> List[Message]:
    """Yield ``email.message.Message`` objects for an ``.mbox`` or ``.eml``."""
    ext = os.path.splitext(path)[1].lower()

    is_mbox = ext == ".mbox"
    is_eml = ext in (".eml", ".msg")
    if not is_mbox and not is_eml:
        # sniff content: mbox if a line begins with the "From " separator.
        try:
            with open(path, "rb") as fh:
                head = fh.read(8192)
        except OSError:
            head = b""
        is_mbox = bool(_MBOX_FROM.search(head)) or head.startswith(b"From ")

    if is_mbox:
        import mailbox

        box = mailbox.mbox(path)
        try:
            return [m for m in box]
        finally:
            box.close()

    with open(path, "rb") as fh:
        return [email.message_from_binary_file(fh)]


def parse(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    ex_target: Optional[str] = _fix(target).strip() if target else None

    try:
        messages = _iter_messages(path)
    except (OSError, ValueError):
        messages = []

    parsed: List[NormalizedMessage] = []
    owner: Optional[str] = None  # heuristic key when no target: first sender

    for msg in messages:
        try:
            sender, addr = _sender_of(msg)
            body = _clean_body(_extract_body(msg))
            text = _fix(body).strip()
            if not text:
                # media-only / empty / attachment-only mail — no usable body
                continue
            ts = _ts_of(msg)

            if ex_target is not None:
                direction = "in" if _matches_target(sender, addr, ex_target) else "out"
            else:
                key = (sender or addr).lower()
                if owner is None:
                    owner = key
                direction = "out" if key == owner else "in"

            parsed.append(
                NormalizedMessage(sender=sender, ts=ts, text=text, direction=direction)
            )
        except Exception:
            # be tolerant: skip a malformed record rather than failing the import
            continue

    parsed.sort(key=lambda m: m.ts)
    return parsed
