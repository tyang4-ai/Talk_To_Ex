"""Content-routed local-model selection — the hybrid brain.

The friend's uploaded chat log decides which local Ollama model voices the
persona: a **Chinese-dominant** log routes to **Qwen** (the strongest open
bilingual zh model), an **English-dominant** log routes to **Gemma**. The choice
is computed once at distill time from the normalized transcript and stored on the
persona (``meta_json["llm_model"]``); the live engine reads it per reply, so a
given persona always answers on the model that best fits its language.

Extending this is deliberately a one-function job: add a language and a
``settings.ollama_model_<lang>`` mapping in ``model_for_language``.
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple, Union

from ..config import settings

# CJK Unified Ideographs (+ Ext-A + Compatibility) — covers Chinese characters.
_CJK = re.compile("[㐀-䶿一-鿿豈-﫿]")
_LATIN = re.compile(r"[A-Za-z]")

Message = Union[str, dict, object]


def _text_of(m: Message) -> str:
    """Pull the message text out of a normalized dict / dataclass / raw string."""
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        return str(m.get("text") or m.get("body") or "")
    return str(getattr(m, "text", "") or "")


def cjk_ratio(text: str) -> float:
    """Fraction of *scripted* characters that are CJK, i.e. cjk / (cjk + latin).

    Spaces, digits and punctuation are ignored so the ratio reflects the
    language of the words, not formatting. Returns 0.0 when the text contains
    no Chinese character and no Latin letter at all.
    """
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    total = cjk + latin
    return cjk / total if total else 0.0


def detect_dominant_language(messages: Iterable[Message]) -> str:
    """Return ``"zh"`` if the transcript is Chinese-dominant, else ``"en"``.

    Dominance is the combined CJK-vs-Latin character ratio across all message
    text, compared against ``settings.model_route_cjk_threshold`` (default 0.5,
    i.e. simple majority). An empty / scriptless transcript falls back to en.
    """
    blob = " ".join(_text_of(m) for m in messages)
    return "zh" if cjk_ratio(blob) >= settings.model_route_cjk_threshold else "en"


def model_for_language(lang: str) -> str:
    """Map a detected language to the configured Ollama model name."""
    return settings.ollama_model_zh if lang == "zh" else settings.ollama_model_en


def pick_model(messages: Iterable[Message]) -> Tuple[str, str]:
    """Convenience: return ``(language, model)`` for a whole transcript."""
    lang = detect_dominant_language(messages)
    return lang, model_for_language(lang)
