"""Rolling conversation summary. Every ~25 messages we ask the local model to
fold the recent turns + prior summary into a fresh compact summary, stored on
``conversation.summary``. Raw turns remain the source of truth (spec §9); the
summary is a derived convenience to keep the live prompt inside the context
budget.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from . import history
from .ollama_client import OllamaClient

# How often (in messages) to refresh the rolling summary. Not a tunable secret,
# so it lives here rather than in settings.
SUMMARY_EVERY = 25


def _build_messages(conv_summary: str, recent_msgs: list) -> list[dict]:
    lines = []
    for m in recent_msgs:
        who = "them" if m.direction == "in" else "me"
        lines.append(f"{who}: {m.body}")
    transcript = "\n".join(lines)
    system = (
        "You compress a text-message conversation into a short running summary. "
        "Keep it factual and neutral: who they are to each other, recurring "
        "topics, open threads, and the current mood. 4-6 sentences max. "
        "Preserve the original language(s) of the conversation (Chinese and/or "
        "English) — do not translate."
    )
    prev = conv_summary.strip() or "(none yet)"
    user = (
        f"Previous summary:\n{prev}\n\n"
        f"Recent messages:\n{transcript}\n\n"
        "Write the updated running summary."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def maybe_resummarize(
    session: Session,
    conv,
    client: Optional[OllamaClient] = None,
) -> bool:
    """If the conversation has hit a ~25-message boundary, refresh its summary.

    Returns True if a resummarization ran. ``client`` is injected in tests; the
    real :class:`OllamaClient` is built lazily only when actually summarizing.
    """
    count = conv.message_count or 0
    if count == 0 or count % SUMMARY_EVERY != 0:
        return False

    client = client or OllamaClient()
    recent_msgs = history.recent(session, conv, n=SUMMARY_EVERY)
    messages = _build_messages(conv.summary or "", recent_msgs)
    new_summary = client.chat(messages, temperature=0.3).strip()

    conv.summary = new_summary
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return True
