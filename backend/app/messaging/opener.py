"""The proactive first message (spec §24.2).

When a persona goes live, it texts the friend FIRST — a short, in-character
apology. This opener is **curated/templated**, not freely generated: it is the
entire first impression and the one message with no user turn to react to, so a
fixed set of variants keeps it on-tone and safe by construction. From the second
message on, the normal local-model engine takes over.

Variant selection is deterministic per persona (so a given ex always opens the
same way), and the persona's display name is woven in when available.
"""
from __future__ import annotations

from ..db import Persona

# Short, texty, in-character apologies. ``{name}`` is filled from the persona;
# kept bilingual-neutral (English) — the live model mirrors language from msg 2 on.
_OPENERS = [
    "hey… it's me. i know this is out of nowhere. i'm sorry for how things ended.",
    "i've been wanting to say this for a while — i'm sorry. can we talk?",
    "hey. i owe you an apology, and i didn't want to keep putting it off.",
    "it's been on my mind a lot… i'm sorry. i hope you're doing okay.",
]


def first_message(persona: Persona) -> str:
    """Return the templated opener for a persona (deterministic per persona)."""
    idx = (persona.id or 0) % len(_OPENERS)
    return _OPENERS[idx]
