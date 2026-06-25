"""Local, keyless distillation fallback for DEMO_MODE (no Claude).

Builds a *structurally valid* ``PersonaArtifacts`` (all 5 persona layers populated)
directly from the normalized transcript + intake — instant, deterministic, never
network-dependent. The live VOICE still comes from the local Ollama model reading
this persona; the distilled layers just need to be present and grounded in the
real chat, which a heuristic does reliably (a 14B model often emits non-conforming
JSON for the full distill prompt). Used only when ``settings.demo_mode`` is on and
no Claude client is injected.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, List

from ..convo.model_router import detect_dominant_language
from .schema import (
    Layer0Core,
    Layer1Identity,
    Layer2Expression,
    Layer3EmotionalLogic,
    Layer4RelationshipBehavior,
    Layer5Boundaries,
    PersonaArtifacts,
    PersonaJSON,
)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "ex"


def _text(m: Any) -> str:
    if isinstance(m, dict):
        return str(m.get("text") or m.get("body") or "").strip()
    return str(getattr(m, "text", "") or "").strip()


def _direction(m: Any) -> str:
    if isinstance(m, dict):
        return str(m.get("direction") or "")
    return str(getattr(m, "direction", "") or "")


def _sender(m: Any) -> str:
    if isinstance(m, dict):
        return str(m.get("sender") or "")
    return str(getattr(m, "sender", "") or "")


def _top_short_lines(lines: List[str], n: int = 6) -> List[str]:
    """The most frequent short (texty) lines — a decent proxy for catchphrases."""
    short = [ln for ln in lines if 0 < len(ln) <= 24]
    common = [ln for ln, _ in Counter(short).most_common(n)]
    return common or lines[:n]


def distill_local(transcript: List[Any], intake: dict) -> PersonaArtifacts:
    """Heuristically build a valid PersonaArtifacts from the chat + intake."""
    intake = intake or {}
    name = (intake.get("nickname") or "").strip() or "your ex"
    slug = _slugify(name)
    tags = list(intake.get("personality_tags") or [])
    attachment = str(intake.get("attachment_style") or "")
    how_met = str(intake.get("how_you_met") or "")
    since = str(intake.get("time_since_breakup") or "")

    ex_lines = [_text(m) for m in transcript if _direction(m) == "in" and _text(m)]
    catchphrases = _top_short_lines(ex_lines, 6)
    examples = ex_lines[:8]

    persona = PersonaJSON(
        name=name,
        slug=slug,
        layer0_core=Layer0Core(
            summary=f"{name}, distilled locally from {len(transcript)} real messages.",
            behavioral_rules=[
                "texts the way they actually did in the chat history",
                "stays casual and short, like real SMS",
            ],
            tags=tags,
        ),
        layer1_identity=Layer1Identity(
            attachment_style=attachment,
            relationship_history=f"{how_met}. Broke up {since}." if how_met or since else "",
        ),
        layer2_expression=Layer2Expression(
            catchphrases=catchphrases,
            examples=examples,
            message_habits="short, fragmentary, lowercase, texty — like real SMS",
            language_rule="reply in the same language the user just used",
        ),
        layer3_emotional_logic=Layer3EmotionalLogic(priorities=tags[:3]),
        layer4_relationship_behavior=Layer4RelationshipBehavior(
            with_partner=f"history: {how_met}" if how_met else "",
        ),
        layer5_boundaries=Layer5Boundaries(),
    )

    persona_md = (
        f"# {name}\n\n"
        f"Distilled locally (demo mode) from {len(transcript)} messages.\n\n"
        f"- How you met: {how_met or '—'}\n"
        f"- Time since breakup: {since or '—'}\n"
        f"- Attachment style: {attachment or '—'}\n"
        f"- Personality: {', '.join(tags) if tags else '—'}\n\n"
        "## Voice\n"
        + ("\n".join(f"- “{c}”" for c in catchphrases) or "- (texty, casual)")
    )
    memories_md = "## Memories (sampled from the real chat)\n" + (
        "\n".join(f"- “{ln}”" for ln in examples) or "- (none)"
    )
    meta = {
        "name": name,
        "slug": slug,
        "personality_tags": tags,
        "attachment": attachment,
        "version": 1,
        "distilled_by": "local-demo",
        "language": detect_dominant_language(transcript),
    }
    return PersonaArtifacts(
        persona_md=persona_md,
        memories_md=memories_md,
        meta=meta,
        persona_json=persona.model_dump(),
    )
