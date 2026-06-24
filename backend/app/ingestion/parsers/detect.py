"""Format auto-detection. The friend never picks a format — we sniff the file.

Order matters: binary/magic checks first, then structural text checks, then a
plaintext fallback that always succeeds.
"""
from __future__ import annotations

import json
import os
import re
import zipfile
from typing import Literal

Format = Literal["imessage", "instagram", "whatsapp", "wechat", "sms", "plaintext"]

SQLITE_MAGIC = b"SQLite format 3\x00"

# WhatsApp _chat.txt header: iOS "[D/M/Y, H:M:S] Sender:" or
# Android "M/D/Y, H:M[ ]AM - Sender:". U+200E / BOM may lead the line.
# Both shapes are WhatsApp-specific: iOS wraps the timestamp in [...]; Android
# uses "date, time<ampm?> - " (the " - " before the sender is the tell, and
# distinguishes it from WeChat/plaintext "date time sender:" lines).
_WA_IOS = re.compile(r"^\s*[‎﻿]*\[\d{1,4}[./-]\d{1,2}[./-]\d{1,4}[,\s]")
_WA_ANDROID = re.compile(
    r"^\s*[‎﻿]*\d{1,4}[./-]\d{1,2}[./-]\d{1,4},\s+"
    r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm]|上午|下午)?\s*-\s+"
)


def _read_head(path: str, n: int = 65536) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


def _looks_like_instagram_json(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    # new schema: messages[] + participants/title ; old: messages + sender_name
    if "messages" in obj and isinstance(obj["messages"], list):
        return True
    if "participants" in obj and "messages" in obj:
        return True
    return False


def detect_format(path: str) -> Format:
    head = _read_head(path)

    # 1. SQLite (iMessage sms.db, or an encrypted WeChat DB — both magic-detect;
    #    the wechat parser raises ParserNeedsManualExport for encrypted ones).
    if head.startswith(SQLITE_MAGIC):
        return "imessage"

    # 2. Instagram "Download Your Information" — a .zip of message_*.json, or a
    #    single message_1.json. Sniff zip members or top-level JSON keys.
    if head.startswith(b"PK\x03\x04") and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                low = name.lower()
                if "messages/inbox" in low and low.endswith(".json"):
                    return "instagram"
        # zip without IG structure → treat as plaintext-unsupported archive
        return "plaintext"

    # decode the head once for the text-based sniffs
    text_head = head.decode("utf-8", errors="ignore").lstrip("﻿").lstrip()

    # 3. JSON: Instagram message export (object with messages[]).
    stripped = text_head.lstrip()
    if stripped[:1] in "{[":
        try:
            obj = json.loads(_read_head(path, 2_000_000).decode("utf-8", "ignore"))
        except (ValueError, UnicodeDecodeError):
            obj = None
        if _looks_like_instagram_json(obj):
            return "instagram"

    # 4. Android "SMS Backup & Restore" XML — <smses ...> or <?xml ...><smses>.
    low_head = text_head.lower()
    if "<smses" in low_head or "<sms " in low_head or "<mms " in low_head:
        return "sms"

    # 5. WhatsApp _chat.txt header lines.
    first_line = text_head.splitlines()[0] if text_head.splitlines() else ""
    if _WA_IOS.match(first_line) or _WA_ANDROID.match(first_line):
        return "whatsapp"
    if os.path.basename(path).lower().endswith("_chat.txt"):
        return "whatsapp"

    # 6. WeChat exported .txt/.csv/.html (best-effort) — only by extension hint,
    #    since its plaintext export overlaps with generic text.
    ext = os.path.splitext(path)[1].lower()
    base = os.path.basename(path).lower()
    if ext in (".html", ".htm") or ext == ".csv" or "wechat" in base or "微信" in base:
        return "wechat"

    # 7. Everything else → plaintext / PDF fallback (always works).
    return "plaintext"
