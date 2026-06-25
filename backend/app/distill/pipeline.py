"""Distillation pipeline (Claude + vendored/adapted ex-skill prompts).

``distill(transcript, intake, client=None)`` turns a normalized transcript plus
intake answers into :class:`PersonaArtifacts` (persona.md + memories.md +
persona.json + meta).

The ``anthropic`` client is **injected** (spec / plan E2): the default is the
real SDK client, constructed lazily so a missing ``ANTHROPIC_API_KEY`` only
fails when an actual API call is made — never at import. Tests pass a fake client
that returns a canned response, so the suite runs with no network and no keys.

Contract with the model
------------------------
The system prompt concatenates the adapted builder prompts; the user message
carries the intake + transcript. The model returns **one JSON envelope** (raw or
inside a ```json fence) with keys ``persona_md``, ``memories_md``,
``persona_json`` and ``meta``. We parse that envelope into ``PersonaArtifacts``.
This keeps live assembly deterministic and the test fake trivial.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..config import require, settings
from .schema import PersonaArtifacts, PersonaJSON

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Prompts that compose the system instruction for the one-shot distillation call.
_BUILDER_PROMPTS = (
    "intake.md",
    "persona_analyzer.md",
    "persona_builder.md",
    "memories_analyzer.md",
    "memories_builder.md",
)

_MAX_TRANSCRIPT_LINES = 4000  # budget guard for very large exports


def load_prompt(name: str) -> str:
    """Read a prompt markdown asset by filename (e.g. ``persona_builder.md``)."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _default_client():
    """Construct the real anthropic client lazily (only when no fake injected).

    Importing/constructing must not require a key; ``require`` raises only here,
    at the boundary where a real call is about to happen.
    """
    import anthropic  # local import so the package isn't needed for tests

    return anthropic.Anthropic(api_key=require("anthropic_api_key"))


def _system_prompt() -> str:
    parts: List[str] = [
        "You are a persona distillation engine for a self-hosted SMS service. "
        "Using the adapted ex-skill prompts below, analyze the chat transcript "
        "and intake, then emit BOTH human-editable markdown and a machine-"
        "readable persona.json.\n\n"
        "Mixed Chinese/English input is expected — preserve original phrasing; "
        "never translate quotes away.\n\n"
        "Return ONE JSON object (optionally inside a ```json fence) with exactly "
        "these keys:\n"
        '  "persona_md": str   — the 5-layer persona document\n'
        '  "memories_md": str  — the shared-history document\n'
        '  "persona_json": obj — the 5-layer machine-readable persona (Layers 0-5)\n'
        '  "meta": obj         — name, slug, profile, personality_tags[], '
        "attachment, knowledge_sources[], corrections_count, version\n"
        "Output nothing outside that JSON object.",
    ]
    for name in _BUILDER_PROMPTS:
        parts.append(f"\n\n===== {name} =====\n{load_prompt(name)}")
    return "".join(parts)


def _render_transcript(transcript: Sequence[Any]) -> str:
    """Render a NormalizedTranscript (or list of dicts) into prompt text.

    Accepts either ``NormalizedMessage`` dataclasses (attrs ``sender``, ``ts``,
    ``text``, ``direction``) or plain dicts with the same keys, so the pipeline
    does not hard-depend on E1's parser package being importable.
    """
    lines: List[str] = []
    for m in transcript[:_MAX_TRANSCRIPT_LINES]:
        if isinstance(m, dict):
            sender = m.get("sender", "")
            ts = m.get("ts", "")
            text = m.get("text", "")
            direction = m.get("direction", "")
        else:
            sender = getattr(m, "sender", "")
            ts = getattr(m, "ts", "")
            text = getattr(m, "text", "")
            direction = getattr(m, "direction", "")
        ts_s = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        lines.append(f"[{ts_s}] ({direction}) {sender}: {text}")
    return "\n".join(lines)


def _user_message(transcript: Sequence[Any], intake: Dict[str, Any]) -> str:
    return (
        "INTAKE (3-question answers):\n"
        f"{json.dumps(intake, ensure_ascii=False, indent=2)}\n\n"
        "TRANSCRIPT (normalized, oldest first; (in)=the ex we model, "
        "(out)=the account owner):\n"
        f"{_render_transcript(transcript)}\n"
    )


def _extract_text(response: Any) -> str:
    """Pull the text payload out of an anthropic-style Messages response.

    Real anthropic responses expose ``.content`` as a list of blocks each with a
    ``.text``. We also accept a plain string or an object with ``.text`` so test
    fakes can be minimal.
    """
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    if content is None:
        text = getattr(response, "text", None)
        if text is not None:
            return text
        raise ValueError("anthropic response has no content/text")
    if isinstance(content, str):
        return content
    chunks: List[str] = []
    for block in content:
        block_text = getattr(block, "text", None)
        if block_text is None and isinstance(block, dict):
            block_text = block.get("text")
        if block_text:
            chunks.append(block_text)
    return "".join(chunks)


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _parse_envelope(text: str) -> Dict[str, Any]:
    """Parse the model's JSON envelope, tolerating a ```json fence or prose
    around a single top-level object."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _FENCE_RE.search(text)
    if m:
        return json.loads(m.group(1))
    # last resort: first balanced-looking object slice
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("could not parse JSON envelope from distillation response")


def distill(
    transcript: Sequence[Any],
    intake: Dict[str, Any],
    client: Optional[Any] = None,
) -> PersonaArtifacts:
    """Distill a transcript + intake into :class:`PersonaArtifacts`.

    ``client`` is any object exposing ``messages.create(...)`` (the anthropic
    SDK shape). When ``None``, the real client is built lazily — unless
    ``settings.demo_mode`` is on, in which case a keyless local heuristic builds
    a valid persona (no Claude). An injected client always wins (tests).
    """
    if client is None and settings.demo_mode:
        from .fallback import distill_local

        return distill_local(list(transcript), intake)
    if client is None:
        client = _default_client()

    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=8192,
        system=_system_prompt(),
        messages=[{"role": "user", "content": _user_message(transcript, intake)}],
    )

    envelope = _parse_envelope(_extract_text(response))

    persona_md = envelope.get("persona_md", "")
    memories_md = envelope.get("memories_md", "")
    persona_json = envelope.get("persona_json", {}) or {}
    meta = envelope.get("meta", {}) or {}

    if not isinstance(persona_md, str) or not isinstance(memories_md, str):
        raise ValueError("distillation envelope missing persona_md/memories_md text")

    # Validate the persona_json into the typed 5-layer model, then normalize back
    # to a plain dict so Layers 0-5 are always present & well-formed downstream.
    typed = PersonaJSON.model_validate(persona_json)
    # carry name/slug from meta into persona_json when the model left them blank
    if not typed.name and isinstance(meta.get("name"), str):
        typed.name = meta["name"]
    if not typed.slug and isinstance(meta.get("slug"), str):
        typed.slug = meta["slug"]

    return PersonaArtifacts(
        persona_md=persona_md,
        memories_md=memories_md,
        meta=meta,
        persona_json=typed.model_dump(),
    )
