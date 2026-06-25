"""Normalizer + dispatch. Routes a file through ``detect_format`` to the right
parser, then cleans the resulting transcript into a canonical form and weights
it with bilingual emotional-keyword digesting (reused from ex-skill) so the
distillation step gets the most signal-rich lines first.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

from ftfy import fix_text

from .parsers import (
    discord,
    generic,
    imessage,
    instagram,
    mail,
    plaintext,
    sms,
    telegram,
    wechat,
    whatsapp,
)
from .parsers.base import NormalizedMessage, NormalizedTranscript
from .parsers.detect import detect_format

# format name -> parser.parse callable
_PARSERS: Dict[str, Callable[..., NormalizedTranscript]] = {
    "imessage": imessage.parse,
    "instagram": instagram.parse,
    "facebook": instagram.parse,  # same Meta schema
    "whatsapp": whatsapp.parse,
    "wechat": wechat.parse,
    "sms": sms.parse,
    "discord": discord.parse,
    "telegram": telegram.parse,
    "email": mail.parse,
    "generic": generic.parse,
    "plaintext": plaintext.parse,
}

# Bilingual emotional-signal lexicon (ex-skill's sms_parser/wechat_parser digest).
_EMOTION_WORDS = (
    # English
    "love", "miss", "sorry", "hate", "happy", "sad", "angry", "cry", "hurt",
    "forever", "promise", "breakup", "broke up", "ex", "heart", "kiss", "hug",
    "lonely", "jealous", "trust", "forgive", "goodbye", "always", "never",
    "베이비", "babe", "baby", "honey",
    # Chinese
    "爱", "想你", "对不起", "讨厌", "开心", "难过", "生气", "哭", "心碎",
    "永远", "答应", "分手", "宝贝", "亲爱的", "抱抱", "亲亲", "孤单", "吃醋",
    "信任", "原谅", "再见", "想念", "喜欢", "恨", "舍不得", "在乎",
)
_EMOTION_RE = re.compile("|".join(re.escape(w) for w in _EMOTION_WORDS), re.IGNORECASE)


def clean_text(text: str) -> str:
    """Repair mojibake and collapse whitespace without destroying CJK."""
    if not text:
        return ""
    fixed = fix_text(text)
    # collapse runs of spaces/tabs but keep newlines (bubble structure)
    fixed = re.sub(r"[ \t ]+", " ", fixed)
    fixed = re.sub(r"\n{3,}", "\n\n", fixed)
    return fixed.strip()


def normalize(transcript: NormalizedTranscript) -> NormalizedTranscript:
    """Clean every message, drop empties, and sort chronologically (stable)."""
    cleaned: NormalizedTranscript = []
    for m in transcript:
        text = clean_text(m.text)
        if not text:
            continue
        cleaned.append(
            NormalizedMessage(sender=m.sender, ts=m.ts, text=text, direction=m.direction)
        )
    cleaned.sort(key=lambda m: m.ts)
    return cleaned


def emotional_score(text: str) -> int:
    """Count emotional-signal hits (bilingual) — used to weight distillation."""
    return len(_EMOTION_RE.findall(text or ""))


def emotional_digest(
    transcript: NormalizedTranscript, top_k: Optional[int] = None
) -> NormalizedTranscript:
    """Return the most emotionally-loaded messages (ex's voice prioritised),
    preserving chronological order. With ``top_k=None`` returns all scored > 0."""
    scored: List[tuple[int, NormalizedMessage]] = []
    for m in transcript:
        score = emotional_score(m.text)
        if m.direction == "in":  # the ex's own words weigh more
            score += 1 if score else 0
        if score:
            scored.append((score, m))
    if top_k is not None:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        scored = scored[:top_k]
    digest = [m for _score, m in scored]
    digest.sort(key=lambda m: m.ts)
    return digest


def parse_file(path: str, target: Optional[str] = None) -> NormalizedTranscript:
    """Detect the format, run the matching parser, and normalize the output.
    The single entry point Epic E2's ``upload`` calls."""
    fmt = detect_format(path)
    parser = _PARSERS[fmt]
    transcript = parser(path, target)
    return normalize(transcript)
