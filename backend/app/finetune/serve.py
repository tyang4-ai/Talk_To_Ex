"""Serve a fine-tuned adapter as a per-persona Ollama model (spec §23.3 step 4).

Writes a Modelfile (``FROM <base>`` + ``ADAPTER <gguf>`` + a persona stub) and
runs ``ollama create persona-<id>`` on the training host (the 4090). The Modelfile
text is pure/testable; the ``ollama create`` call is injectable (host-only).
"""
from __future__ import annotations

from typing import Callable, Optional

# the in-character / anti-name-leak stub baked into every derived model.
_SYSTEM_STUB = (
    "You are a real person texting an ex. Stay fully in character. You are NOT an "
    "AI, assistant, or language model. Reply in the same language the user just "
    "used. Text casually and short, like real SMS."
)


def persona_model_name(persona_id: int) -> str:
    return f"persona-{persona_id}"


def build_modelfile(base_model: str, gguf_path: str, system: Optional[str] = None) -> str:
    """The Ollama Modelfile that layers the persona's LoRA adapter on the base."""
    return (
        f"FROM {base_model}\n"
        f"ADAPTER {gguf_path}\n"
        f'SYSTEM """{system or _SYSTEM_STUB}"""\n'
        "PARAMETER num_ctx 8192\n"
        "PARAMETER temperature 0.8\n"
    )


def _default_create(name: str, modelfile: str) -> None:
    raise RuntimeError(
        "`ollama create` is host-only — run it on the training host per "
        "ops/finetune/setup.md; inject ollama_create in tests/CI."
    )


# ollama_create(name, modelfile_text) -> None
Creator = Callable[[str, str], None]


def register_adapter(
    persona_id: int,
    gguf_path: str,
    base_model: str,
    *,
    system: Optional[str] = None,
    ollama_create: Optional[Creator] = None,
) -> str:
    """Create the derived Ollama model for a persona; return its model name."""
    name = persona_model_name(persona_id)
    modelfile = build_modelfile(base_model, gguf_path, system)
    create = ollama_create or _default_create
    create(name, modelfile)
    return name
