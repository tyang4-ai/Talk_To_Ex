"""Format auto-detection. The friend never picks a format — we sniff the file.

Order matters: binary/magic checks first, then structural text checks, then a
plaintext fallback that always succeeds. The JSON family (Meta/Instagram,
Discord, Telegram, generic) is disambiguated by signature keys, most-specific
first, with a substring fallback for files too large to fully parse.
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from typing import List, Optional

Format = str  # one of the keys below; kept loose so registries stay in sync

SQLITE_MAGIC = b"SQLite format 3\x00"

# WhatsApp _chat.txt header: iOS "[D/M/Y, H:M:S] Sender:" or
# Android "M/D/Y, H:M[ ]AM - Sender:". U+200E / BOM may lead the line.
_WA_IOS = re.compile(r"^\s*[‎﻿]*\[\d{1,4}[./-]\d{1,2}[./-]\d{1,4}[,\s]")
_WA_ANDROID = re.compile(
    r"^\s*[‎﻿]*\d{1,4}[./-]\d{1,2}[./-]\d{1,4},\s+"
    r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm]|上午|下午)?\s*-\s+"
)

# An mbox starts a message with a "From " separator that ends in a year.
_MBOX_FROM = re.compile(rb"^From .{0,200}\d{4}", re.MULTILINE)
_EML_HEADER = re.compile(r"(?im)^(from|to|subject|date|message-id|received|return-path)\s*:")

# Telegram Desktop top-level chat kinds.
_TG_KINDS = {
    "personal_chat", "private_group", "private_supergroup", "saved_messages",
    "public_channel", "public_supergroup", "bot_chat", "private_channel",
}

_SENDER_KEYS = {"sender", "from", "author", "name", "who", "user", "speaker"}
_TEXT_KEYS = {"message", "content", "text", "body", "msg"}


def _read_head(path: str, n: int = 65536) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def _first_dicts(items: object, k: int = 25) -> List[dict]:
    if not isinstance(items, list):
        return []
    return [x for x in items[:k] if isinstance(x, dict)]


# --- JSON family signature predicates (most specific first) ----------------
def _is_meta_json(obj: object) -> bool:
    """Instagram / Facebook Messenger 'Download Your Information' JSON."""
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get("participants"), list) and "messages" in obj:
        return True
    for m in _first_dicts(obj.get("messages")):
        if "sender_name" in m or "timestamp_ms" in m:
            return True
    return False


def _is_discord_json(obj: object) -> bool:
    """DiscordChatExporter: per-message author OBJECT, or top-level channel/guild."""
    if isinstance(obj, dict):
        if isinstance(obj.get("messages"), list) and (
            isinstance(obj.get("channel"), dict) or isinstance(obj.get("guild"), dict)
        ):
            return True
        for m in _first_dicts(obj.get("messages")):
            if isinstance(m.get("author"), dict):
                return True
    elif isinstance(obj, list):
        for m in _first_dicts(obj):
            if isinstance(m.get("author"), dict) and ("content" in m or "timestamp" in m):
                return True
    return False


def _is_telegram_json(obj: object) -> bool:
    """Telegram Desktop result.json — by top-level chat kind or message markers."""
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get("type"), str) and obj["type"] in _TG_KINDS and isinstance(
        obj.get("messages"), list
    ):
        return True
    for m in _first_dicts(obj.get("messages")):
        if "date_unixtime" in m or "from_id" in m:
            return True
    return False


def _is_generic_chat_json(obj: object) -> bool:
    """Any list-of-objects / {messages:[...]} carrying a text-ish field."""
    items: object = None
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict):
        items = obj.get("messages")
        if not isinstance(items, list):
            for v in obj.values():
                if isinstance(v, list):
                    items = v
                    break
    for m in _first_dicts(items):
        keys = {k.lower() for k in m.keys() if isinstance(k, str)}
        if keys & _TEXT_KEYS:
            return True
    return False


def _sniff_json_text(t: str) -> Optional[str]:
    """Substring fallback when the file is too large to fully parse."""
    has_msgs = '"messages"' in t
    if '"sender_name"' in t or ('"participants"' in t and has_msgs):
        return "instagram"
    if '"date_unixtime"' in t or '"personal_chat"' in t or '"from_id"' in t:
        return "telegram"
    if '"author"' in t and ('"isBot"' in t or '"nickname"' in t or '"DirectTextChat"' in t):
        return "discord"
    return None


def _classify_json(path: str, text_head: str) -> Optional[str]:
    """Identify a JSON chat export, or None if it isn't a recognizable chat."""
    try:
        obj = json.loads(_read_head(path, 8_000_000).decode("utf-8", "ignore"))
    except (ValueError, UnicodeDecodeError):
        obj = None
    if obj is not None:
        if _is_meta_json(obj):
            return "instagram"
        if _is_discord_json(obj):
            return "discord"
        if _is_telegram_json(obj):
            return "telegram"
        if _is_generic_chat_json(obj):
            return "generic"
        return None
    # full parse failed (too large / truncated head) → substring sniff, then
    # hand anything still-jsonish to the tolerant generic parser (it re-reads
    # the whole file with its own loader).
    hit = _sniff_json_text(text_head)
    if hit:
        return hit
    return "generic"


def _zip_meta_label(names: List[str]) -> str:
    joined = " ".join(names).lower()
    if "facebook" in joined or "your_facebook_activity" in joined:
        return "facebook"
    return "instagram"


def detect_format(path: str) -> Format:
    head = _read_head(path)
    ext = os.path.splitext(path)[1].lower()
    base = os.path.basename(path).lower()

    # 1. SQLite (iMessage sms.db, or an encrypted WeChat DB).
    if head.startswith(SQLITE_MAGIC):
        return "imessage"

    # 2. Email by extension (RFC822 mailbox / single message).
    if ext in (".mbox", ".eml"):
        return "email"

    # 3. ZIP exports — Meta (messages/inbox), else sniff JSON members for a
    #    zipped Discord/Telegram export (those parsers handle a zip path).
    if head.startswith(b"PK\x03\x04") and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for name in names:
                low = name.lower()
                if "messages/inbox" in low and low.endswith(".json"):
                    return _zip_meta_label(names)
            for n in sorted(x for x in names if x.lower().endswith(".json") and not x.endswith("/")):
                try:
                    obj = json.loads(zf.read(n)[:8_000_000].decode("utf-8", "ignore"))
                except (ValueError, OSError):
                    continue
                for pred, fmt in (
                    (_is_meta_json, "instagram"),
                    (_is_discord_json, "discord"),
                    (_is_telegram_json, "telegram"),
                ):
                    if pred(obj):
                        return fmt
        return "plaintext"

    # decode the head once for the text-based sniffs
    text_head = head.decode("utf-8", errors="ignore").lstrip("﻿").lstrip()
    stripped = text_head.lstrip()

    # 4. JSON family — Meta/Instagram, Facebook, Discord, Telegram, generic.
    if stripped[:1] in "{[":
        hit = _classify_json(path, text_head)
        if hit is not None:
            return hit

    # 5. Android "SMS Backup & Restore" XML.
    low_head = text_head.lower()
    if "<smses" in low_head or "<sms " in low_head or "<mms " in low_head:
        return "sms"

    # 6. Email by content (mbox separator, or an RFC822 header block).
    if _MBOX_FROM.search(head):
        return "email"
    if stripped[:1].isalpha() and len({h.lower() for h in _EML_HEADER.findall(text_head[:4096])}) >= 2:
        first = (text_head.splitlines() or [""])[0]
        if re.match(r"(?i)^[a-z-]+:\s", first):
            return "email"

    # 7. WhatsApp _chat.txt header lines.
    first_line = text_head.splitlines()[0] if text_head.splitlines() else ""
    if _WA_IOS.match(first_line) or _WA_ANDROID.match(first_line):
        return "whatsapp"
    if base.endswith("_chat.txt"):
        return "whatsapp"

    # 8. CSV family: Discord CSV (AuthorID/Content), WeChat-named, else generic.
    if ext == ".csv":
        fl = first_line.lower()
        if "authorid" in fl and "content" in fl:
            return "discord"
        if "wechat" in base or "微信" in base:
            return "wechat"
        return "generic"

    # 9. WeChat exported .html (best-effort) or wechat-named files.
    if ext in (".html", ".htm") or "wechat" in base or "微信" in base:
        return "wechat"

    # 10. Everything else → plaintext / PDF fallback (always works).
    return "plaintext"
