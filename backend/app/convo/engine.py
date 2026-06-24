"""Live conversation engine.

``reply()`` assembles the deterministic local-model prompt for one inbound text
and returns a list of SMS bubbles. The prompt is built from:

* the **frozen** persona core (Layers 0, 1, 3, 4, 5 — personality/identity/
  emotional-logic/relationship/boundaries),
* the **latest style overlay** (Layer 2 — expression/voice, swapped in by the
  periodic style tuner; §9.1),
* the rolling conversation summary,
* the most recent raw turns,
* an SMS-native few-shot, and
* an explicit language-mirroring rule (Qwen code-switches; §9).

The model emits bubbles separated by the delimiter ``\\n---\\n``; we split on it.

This function is **read-only** with respect to history: it loads prior context
and treats ``body`` as the latest inbound turn, but it does NOT persist the
inbound message or the reply. The messaging gateway (E4) owns persistence,
summary refresh, and style retuning around this call.

Persona contract (owned by E2): the machine-readable 5-layer ``persona_json``
lives in the plaintext ``meta_json`` column under the ``"persona_json"`` key
(see ``persona/store.save_artifacts``). The latest Layer-2 overlay lives,
encrypted, in ``style_overlay_enc`` under the ``"layer2_expression"`` key.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session, select

from .. import crypto
from ..db import Conversation, Persona
from ..distill.schema import CORE_LAYERS, PersonaJSON
from .history import recent
from .ollama_client import OllamaClient

# The model emits this between message bubbles; the app splits and sends each as
# a separate Twilio message.
BUBBLE_DELIMITER = "\n---\n"

# JSON key (in persona_json / the style overlay) for the expression layer.
STYLE_LAYER_KEY = "layer2_expression"

# Human labels for the frozen core layers, keyed by index (for prompt headers).
_LAYER_LABELS = {
    0: "core personality",
    1: "identity",
    2: "expression / voice",
    3: "emotional logic",
    4: "relationship behavior",
    5: "boundaries",
}

LANGUAGE_RULE = (
    "LANGUAGE: Always reply in the same language the user just used. If they "
    "text in Chinese, reply in Chinese; if English, reply in English; if they "
    "mix the two, mirror that mix. Never switch languages on your own."
)

SMS_STYLE_RULE = (
    "FORMAT: You are texting on a phone, not writing an essay. Keep it short, "
    "casual, and fragmentary — lowercase is fine, abbreviations are fine. Send "
    "1-3 short bubbles. Separate each bubble with a line containing only '---'. "
    "Do not use markdown, headers, or bullet points."
)

# A tiny SMS-native few-shot so the model learns the bubble format + texty tone.
SMS_FEW_SHOT: list[dict] = [
    {"role": "user", "content": "hey you up?"},
    {"role": "assistant", "content": "ya\n---\nwhats up"},
    {"role": "user", "content": "在吗 想你了"},
    {"role": "assistant", "content": "在啊\n---\n怎么突然这么说"},
]


def _load_persona_json(persona: Persona) -> dict:
    """Load the 5-layer machine-readable persona_json from ``meta_json``.

    E2's ``persona/store`` nests the full ``persona_json`` under the
    ``"persona_json"`` key of the plaintext ``meta_json`` column. Returns ``{}``
    if nothing parses, so prompt assembly still works from ``persona.name`` alone.
    """
    try:
        meta = json.loads(persona.meta_json or "{}")
    except Exception:
        return {}
    pj = meta.get("persona_json")
    return pj if isinstance(pj, dict) else {}


def _load_style_overlay(persona: Persona) -> dict:
    """Decrypt + parse the latest Layer-2 style overlay, or ``{}`` if none."""
    if not persona.style_overlay_enc:
        return {}
    try:
        obj = json.loads(crypto.dec_str(persona.style_overlay_enc))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def get_or_create_conversation(
    session: Session, persona_id: int, peer_e164: str
) -> Conversation:
    """Look up (or create) the conversation thread for this persona + peer."""
    stmt = select(Conversation).where(
        Conversation.persona_id == persona_id,
        Conversation.peer_e164 == peer_e164,
    )
    conv = session.exec(stmt).first()
    if conv is None:
        conv = Conversation(persona_id=persona_id, peer_e164=peer_e164)
        session.add(conv)
        session.commit()
        session.refresh(conv)
    return conv


def _render(value) -> str:
    """Render a layer model-dump / dict into compact, CJK-readable prompt text."""
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_system_prompt(persona: Persona) -> str:
    """Assemble the system prompt from frozen core layers + the Layer-2 overlay."""
    pj = _load_persona_json(persona)
    overlay = _load_style_overlay(persona)

    parts: list[str] = []
    parts.append(
        f"You are {persona.name}. Stay fully in character as {persona.name} at "
        f"all times. You are NOT an AI or assistant — never mention models, "
        f"Qwen, or being artificial. You are a real person texting an ex."
    )

    # Frozen core layers, rendered via E2's typed model so key names stay in sync.
    if pj:
        typed = PersonaJSON.model_validate(pj)
        for idx in CORE_LAYERS:
            label = _LAYER_LABELS.get(idx, f"layer {idx}")
            section = typed.layer(idx).model_dump()
            parts.append(f"[Layer {idx} — {label}]\n{_render(section)}")

    # Live voice: prefer the freshest style overlay (Layer 2), else the distilled
    # Layer 2 from persona_json.
    style = overlay.get(STYLE_LAYER_KEY) or pj.get(STYLE_LAYER_KEY)
    if style:
        parts.append(f"[Layer 2 — current voice]\n{_render(style)}")

    parts.append(SMS_STYLE_RULE)
    parts.append(LANGUAGE_RULE)
    return "\n\n".join(parts)


def split_bubbles(text: str) -> list[str]:
    """Split the model output into non-empty bubbles on the delimiter."""
    raw = text.split(BUBBLE_DELIMITER)
    bubbles = [b.strip() for b in raw if b.strip()]
    return bubbles or ([text.strip()] if text.strip() else [])


def reply(
    session: Session,
    persona_id: int,
    peer_e164: str,
    body: str,
    ollama: Optional[OllamaClient] = None,
) -> list[str]:
    """Generate the persona's reply to ``body`` as a list of SMS bubbles.

    ``ollama`` is injected in tests (any object with a ``chat(messages, ...)``
    method); in production the real :class:`OllamaClient` is built lazily.
    """
    persona = session.get(Persona, persona_id)
    if persona is None:
        raise ValueError(f"persona {persona_id} not found")

    conv = get_or_create_conversation(session, persona_id, peer_e164)

    system_prompt = build_system_prompt(persona)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(SMS_FEW_SHOT)

    if conv.summary:
        messages.append(
            {
                "role": "system",
                "content": f"Context so far (running summary):\n{conv.summary}",
            }
        )

    for m in recent(session, conv, n=20):
        role = "user" if m.direction == "in" else "assistant"
        messages.append({"role": role, "content": m.body})

    # The latest inbound turn (not yet persisted — E4 persists after sending).
    messages.append({"role": "user", "content": body})

    client = ollama or OllamaClient()
    out = client.chat(messages)
    return split_bubbles(out)
