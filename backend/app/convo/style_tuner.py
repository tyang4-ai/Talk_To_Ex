"""Periodic style re-tuning (§9.1) — the *second* use of the Claude API.

Every ``settings.style_retune_every`` messages (per conversation), ask Claude to
refine the persona's **expression/voice** (Layer 2) using the last ~100 turns,
while keeping the core personality frozen. A post-step validation
(:func:`validate_core_unchanged`) diffs the returned core layers (0/1/3/4/5)
against the immutable distilled original and **rejects** the overlay if any core
layer changed. On success we persist only the new Layer-2 overlay to
``persona.style_overlay_enc`` plus a :class:`StyleTuning` history row.

The personality stays constant; only the voice adapts.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session

from .. import crypto
from ..config import require, settings
from ..db import Conversation, Persona, StyleTuning
from ..distill.schema import CORE_LAYERS, STYLE_LAYER, PersonaJSON
from .engine import STYLE_LAYER_KEY, _load_persona_json
from .history import recent


class CoreLayerMutated(Exception):
    """Raised when a re-tune overlay would alter a frozen core persona layer."""

    def __init__(self, changed: list[int]) -> None:
        self.changed = changed
        super().__init__(
            "style re-tune rejected: core layers changed: "
            + ", ".join(str(i) for i in changed)
        )


def _make_anthropic_client():
    """Build the real Anthropic client lazily (key required only here, not at import)."""
    import anthropic

    return anthropic.Anthropic(api_key=require("anthropic_api_key"))


def validate_core_unchanged(original: dict, overlay: dict) -> None:
    """Raise :class:`CoreLayerMutated` if any frozen core layer differs.

    Only Layer 2 (expression) may change. We compare via E2's typed
    :class:`PersonaJSON` so the comparison stays synced with the schema and both
    sides are normalized before diffing (BaseModel equality compares fields).
    """
    o = PersonaJSON.model_validate(original)
    n = PersonaJSON.model_validate(overlay)
    changed = [idx for idx in CORE_LAYERS if o.layer(idx) != n.layer(idx)]
    if changed:
        raise CoreLayerMutated(changed)


def _build_messages(original: dict, recent_msgs: list, meta: dict) -> list[dict]:
    lines = []
    for m in recent_msgs:
        who = "them" if m.direction == "in" else "me"
        lines.append(f"{who}: {m.body}")
    transcript = "\n".join(lines)

    system = (
        "You refine the EXPRESSION/STYLE of an existing persona so it keeps pace "
        "with an ongoing text conversation — picking up current vocabulary, "
        "sentence length, emoji/punctuation habits, cadence, and shared "
        "references. You return the persona as JSON with the same keys as the "
        "original (name, slug, layer0_core .. layer5_boundaries, corrections). "
        "HARD RULE: you may ONLY change layer2_expression. Copy layer0_core, "
        "layer1_identity, layer3_emotional_logic, layer4_relationship_behavior, "
        "and layer5_boundaries through UNCHANGED, verbatim, from the original. "
        "Do not alter core personality, identity, emotional logic, relationship "
        "behavior, or boundaries. Preserve the original language(s) (Chinese "
        "and/or English). Respond with JSON only."
    )
    user = (
        "Original persona (frozen — copy every non-layer2_expression layer "
        "verbatim):\n"
        f"{json.dumps(original, ensure_ascii=False, indent=2)}\n\n"
        f"meta:\n{json.dumps(meta, ensure_ascii=False)}\n\n"
        "Recent conversation:\n"
        f"{transcript}\n\n"
        "Return the full persona JSON with only layer2_expression updated."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _call_claude(client, messages: list[dict]) -> dict:
    """Invoke the (real or fake) Anthropic client and parse the JSON overlay.

    System goes in the top-level ``system`` arg (Anthropic API shape); the rest
    are passed as messages. A fake client in tests just needs to return an object
    whose ``.content[0].text`` is the JSON persona.
    """
    system = ""
    convo = []
    for m in messages:
        if m["role"] == "system":
            system = m["content"]
        else:
            convo.append(m)

    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=system,
        messages=convo,
    )
    text = resp.content[0].text
    return json.loads(text)


def maybe_retune(
    session: Session,
    conv: Conversation,
    client=None,
) -> Optional[StyleTuning]:
    """If at a retune boundary, fetch a new Layer-2 overlay from Claude and save it.

    Returns the persisted :class:`StyleTuning` row on success, or ``None`` if it
    was not a boundary. Raises :class:`CoreLayerMutated` (and writes nothing) if
    the returned overlay tampers with a frozen core layer.
    """
    every = settings.style_retune_every
    count = conv.message_count or 0
    if count == 0 or every <= 0 or count % every != 0:
        return None

    persona = session.get(Persona, conv.persona_id)
    if persona is None:
        return None

    original = _load_persona_json(persona)
    try:
        meta = json.loads(persona.meta_json or "{}")
    except Exception:
        meta = {}

    recent_msgs = recent(session, conv, n=100)

    client = client or _make_anthropic_client()
    messages = _build_messages(original, recent_msgs, meta)
    overlay = _call_claude(client, messages)

    # Guardrail: reject (and persist nothing) if a frozen core layer changed.
    validate_core_unchanged(original, overlay)

    # Accept: persist ONLY the new Layer-2 (expression) overlay + a history row.
    layer2 = PersonaJSON.model_validate(overlay).layer(STYLE_LAYER).model_dump()
    overlay_to_store = {STYLE_LAYER_KEY: layer2}
    overlay_json = json.dumps(overlay_to_store, ensure_ascii=False)

    persona.style_overlay_enc = crypto.enc_str(overlay_json)
    session.add(persona)

    tuning = StyleTuning(
        persona_id=persona.id,
        conversation_id=conv.id,
        overlay_json_enc=crypto.enc_str(overlay_json),
        msg_count_at_run=count,
    )
    session.add(tuning)

    session.commit()
    session.refresh(tuning)
    return tuning
