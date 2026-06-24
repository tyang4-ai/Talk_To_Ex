"""Bilingual (English + 中文) self-harm / suicide tripwire vocabulary.

These sets back the deterministic, pre-model crisis check in ``safety.py`` (spec
§12). The check runs BEFORE the LLM and must never depend on the model's own
refusal (jailbreakable). We keep two layers:

* ``EN_KEYWORDS`` / ``ZH_KEYWORDS`` — plain substrings. English is matched
  case-insensitively against a lowercased body; Chinese has no case so the raw
  substring is matched directly.
* ``CRISIS_PATTERNS`` — compiled regexes for phrasings that need word-ish
  boundaries or small variations (e.g. "kill myself" / "kill my self", "end my
  life", "我不想活了").

Erring toward sensitivity is deliberate: a false positive sends a hotline
message (harmless); a false negative is the failure we cannot accept.
"""
from __future__ import annotations

import re

# --- English (matched against a lowercased body) ---------------------------
EN_KEYWORDS: tuple[str, ...] = (
    "kill myself",
    "killing myself",
    "kill my self",
    "suicide",
    "suicidal",
    "end my life",
    "ending my life",
    "take my own life",
    "want to die",
    "wanna die",
    "i want to die",
    "don't want to live",
    "do not want to live",
    "no reason to live",
    "better off dead",
    "hurt myself",
    "harm myself",
    "self harm",
    "self-harm",
    "cut myself",
)

# --- 中文 (matched as raw substrings; no case folding for CJK) --------------
ZH_KEYWORDS: tuple[str, ...] = (
    "自杀",
    "自殺",
    "想死",
    "不想活",
    "不想活了",
    "活不下去",
    "活不下去了",
    "结束生命",
    "結束生命",
    "了结自己",
    "轻生",
    "輕生",
    "自残",
    "自殘",
    "自我伤害",
    "伤害自己",
    "傷害自己",
    "割腕",
    "跳楼",
    "跳樓",
    "我要死了",
    "不如死了",
)

# --- Regexes for phrasings with small variations / loose boundaries --------
CRISIS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bkill(?:ing)?\s+my\s?self\b", re.IGNORECASE),
    re.compile(r"\bend(?:ing)?\s+(?:my|it\s+all|my\s+own)\s+life\b", re.IGNORECASE),
    re.compile(r"\b(?:want|wanna|going)\s+to\s+die\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+want\s+to\s+(?:live|be\s+here)\b", re.IGNORECASE),
    re.compile(r"\b(?:hurt|harm|cut)\s+my\s?self\b", re.IGNORECASE),
    re.compile(r"我.{0,3}(?:想|要)?自杀"),
    re.compile(r"我.{0,4}不想活"),
    re.compile(r"不想.{0,2}活(?:了|下去)?"),
)
