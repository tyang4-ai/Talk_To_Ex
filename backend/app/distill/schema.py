"""Typed persona artifacts produced by the distillation pipeline.

The distillation pipeline (``distill/pipeline.py``) emits three human-editable
markdown documents (``persona.md``, ``memories.md``) plus a machine-readable
``persona.json`` (spec §11.1 improvement #6) and a ``meta.json`` sidecar.

The ``persona.json`` mirrors the vendored ex-skill 5-layer persona framework so
the live conversation engine can assemble prompts deterministically and the
style tuner (§9.1) can refine *only* Layer 2 while a validator freezes the rest:

- Layer 0 — core personality (relationship labels translated into concrete,
  executable behavioural rules). FROZEN.
- Layer 1 — identity (occupation, MBTI, attachment style, history). FROZEN.
- Layer 2 — expression / style (catchphrases, message habits, emoji, cadence,
  language-mirroring). The ONLY layer the periodic style tuner may modify.
- Layer 3 — emotional logic (priorities, affection, withdrawal). FROZEN.
- Layer 4 — relationship behaviour (partner / friends / family / under stress).
  FROZEN.
- Layer 5 — boundaries (dealbreakers, avoided topics). FROZEN.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Layer indices that the style tuner is forbidden from mutating (everything but
# Layer 2). Imported by ``convo/style_tuner.py`` for the core-freeze guardrail.
CORE_LAYERS: tuple[int, ...] = (0, 1, 3, 4, 5)
STYLE_LAYER: int = 2


class Layer0Core(BaseModel):
    """Core personality — relationship labels -> concrete behavioural rules."""

    summary: str = ""
    behavioral_rules: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class Layer1Identity(BaseModel):
    """Identity facts."""

    occupation: str = ""
    mbti: str = ""
    zodiac: str = ""
    attachment_style: str = ""
    relationship_history: str = ""


class Layer2Expression(BaseModel):
    """Expression / style — the ONLY layer the style tuner may refine."""

    catchphrases: List[str] = Field(default_factory=list)
    message_habits: str = ""
    emoji_usage: str = ""
    sentence_length: str = ""
    cadence: str = ""
    # spec §11.1 #2 — explicit language-mirroring rule lives in Layer 2.
    language_rule: str = "reply in the same language the user just used"
    examples: List[str] = Field(default_factory=list)


class Layer3EmotionalLogic(BaseModel):
    """Emotional logic — priorities, affection, withdrawal, dissatisfaction."""

    priorities: List[str] = Field(default_factory=list)
    affection_expression: str = ""
    withdrawal_pattern: str = ""
    dissatisfaction_signals: List[str] = Field(default_factory=list)


class Layer4RelationshipBehavior(BaseModel):
    """Relational behaviour across contexts."""

    with_partner: str = ""
    with_friends: str = ""
    with_family: str = ""
    under_stress: str = ""
    scenarios: List[str] = Field(default_factory=list)


class Layer5Boundaries(BaseModel):
    """Boundaries, dealbreakers, avoided topics."""

    dealbreakers: List[str] = Field(default_factory=list)
    avoided_topics: List[str] = Field(default_factory=list)
    rejection_style: str = ""


class PersonaJSON(BaseModel):
    """Machine-readable 5-layer persona (Layers 0-5)."""

    name: str = ""
    slug: str = ""
    layer0_core: Layer0Core = Field(default_factory=Layer0Core)
    layer1_identity: Layer1Identity = Field(default_factory=Layer1Identity)
    layer2_expression: Layer2Expression = Field(default_factory=Layer2Expression)
    layer3_emotional_logic: Layer3EmotionalLogic = Field(
        default_factory=Layer3EmotionalLogic
    )
    layer4_relationship_behavior: Layer4RelationshipBehavior = Field(
        default_factory=Layer4RelationshipBehavior
    )
    layer5_boundaries: Layer5Boundaries = Field(default_factory=Layer5Boundaries)
    corrections: List[str] = Field(default_factory=list)

    def layer(self, index: int) -> BaseModel:
        """Return the sub-model for a layer index 0-5 (used by the freeze guard)."""
        mapping = {
            0: self.layer0_core,
            1: self.layer1_identity,
            2: self.layer2_expression,
            3: self.layer3_emotional_logic,
            4: self.layer4_relationship_behavior,
            5: self.layer5_boundaries,
        }
        if index not in mapping:
            raise KeyError(f"persona layer index out of range: {index}")
        return mapping[index]


class PersonaMeta(BaseModel):
    """``meta.json`` sidecar (spec §11 + §11.1 #7 channel/subscription/safety)."""

    name: str = ""
    slug: str = ""
    profile: str = ""
    personality_tags: List[str] = Field(default_factory=list)
    attachment: str = ""
    knowledge_sources: List[str] = Field(default_factory=list)
    corrections_count: int = 0
    version: int = 1
    # §11.1 #7 extensions
    e164: Optional[str] = None
    subscription_status: Optional[str] = None
    kill_switch: bool = False


class PersonaArtifacts(BaseModel):
    """The full distillation output. ``persona_json`` is the machine-readable
    5-layer model; ``meta`` is a free-form dict (the ``persona/store`` persists
    it as ``meta_json`` on the Persona row)."""

    persona_md: str
    memories_md: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    persona_json: Dict[str, Any] = Field(default_factory=dict)

    def parsed_persona(self) -> PersonaJSON:
        """Validate ``persona_json`` into the typed 5-layer model."""
        return PersonaJSON.model_validate(self.persona_json)
