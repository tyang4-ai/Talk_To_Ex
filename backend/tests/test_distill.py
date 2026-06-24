"""E2 distillation pipeline tests — fully mock-based (no anthropic, no keys).

A fake anthropic client returns a canned JSON envelope; we assert the pipeline
parses it into PersonaArtifacts with Layers 0-5 present and well-formed, and that
mixed Chinese/English content survives.
"""
import json
from datetime import datetime

from app.distill.pipeline import distill
from app.distill.schema import PersonaArtifacts, PersonaJSON


# --- fakes -----------------------------------------------------------------


class _Block:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Messages:
    def __init__(self, payload_text, recorder):
        self._payload = payload_text
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.update(kwargs)
        return _Response(self._payload)


class FakeAnthropic:
    """Mimics the anthropic SDK surface: ``client.messages.create(...)``."""

    def __init__(self, payload_text):
        self.last_call = {}
        self.messages = _Messages(payload_text, self.last_call)


def _canned_envelope():
    persona_json = {
        "name": "小美 / Mei",
        "slug": "xiao-mei",
        "layer0_core": {
            "summary": "anxious-attachment, warm but tests you",
            "behavioral_rules": [
                "超过2小时没回会发'你在干嘛?'",
                "denies caring then checks in within an hour",
            ],
            "tags": ["焦虑型", "爱撒娇", "翻旧账"],
        },
        "layer1_identity": {
            "occupation": "designer / 设计",
            "mbti": "ENFP",
            "zodiac": "Gemini / 双子座",
            "attachment_style": "anxious / 焦虑型",
            "relationship_history": "together 3 years, college classmates",
        },
        "layer2_expression": {
            "catchphrases": ["在干嘛呀", "u up?"],
            "message_habits": "fragmentary, double-texts, lowercase",
            "emoji_usage": "～ and 🥺 a lot",
            "sentence_length": "short",
            "cadence": "fast replies when happy, silence when upset",
            "language_rule": "reply in the same language the user just used",
            "examples": ["在干嘛呀\n---\n睡了吗", "u up\n---\nmiss u"],
        },
        "layer3_emotional_logic": {
            "priorities": ["being remembered", "reassurance"],
            "affection_expression": "撒娇 + 小礼物",
            "withdrawal_pattern": "one-word replies '嗯' '哦' before going quiet",
            "dissatisfaction_signals": ["随便你", "算了"],
        },
        "layer4_relationship_behavior": {
            "with_partner": "clingy-warm",
            "with_friends": "social butterfly",
            "with_family": "dutiful but distant",
            "under_stress": "withdraws then explodes",
            "scenarios": ["翻旧账 during fights"],
        },
        "layer5_boundaries": {
            "dealbreakers": ["lying", "被忽视"],
            "avoided_topics": ["her father"],
            "rejection_style": "goes cold, '随便你'",
        },
        "corrections": [],
    }
    envelope = {
        "persona_md": "# 小美 / Mei\n## Layer 0 — Core\n超过2小时会发'你在干嘛?'\n",
        "memories_md": "## 关系概览\nMet in college, together 3 years.\n",
        "persona_json": persona_json,
        "meta": {
            "name": "小美 / Mei",
            "slug": "xiao-mei",
            "personality_tags": ["焦虑型", "爱撒娇"],
            "attachment": "anxious",
            "version": 1,
            "corrections_count": 0,
        },
    }
    return envelope


def _transcript():
    return [
        {
            "sender": "Mei",
            "ts": datetime(2024, 1, 1, 22, 0, 0),
            "text": "在干嘛呀",
            "direction": "in",
        },
        {
            "sender": "me",
            "ts": datetime(2024, 1, 1, 22, 5, 0),
            "text": "nothing much u",
            "direction": "out",
        },
    ]


# --- tests -----------------------------------------------------------------


def test_distill_parses_artifacts_with_layers_0_through_5():
    payload = json.dumps(_canned_envelope(), ensure_ascii=False)
    client = FakeAnthropic(payload)

    arts = distill(_transcript(), {"name": "小美", "slug": "xiao-mei"}, client=client)

    assert isinstance(arts, PersonaArtifacts)
    assert "小美" in arts.persona_md
    assert "关系概览" in arts.memories_md

    # the typed 5-layer model validates and exposes Layers 0-5.
    parsed: PersonaJSON = arts.parsed_persona()
    assert parsed.name == "小美 / Mei"
    for idx in range(6):  # 0..5 all present
        assert parsed.layer(idx) is not None
    assert "超过2小时没回会发'你在干嘛?'" in parsed.layer0_core.behavioral_rules
    assert parsed.layer1_identity.mbti == "ENFP"
    assert "u up?" in parsed.layer2_expression.catchphrases
    assert parsed.layer2_expression.language_rule
    assert parsed.layer3_emotional_logic.dissatisfaction_signals
    assert parsed.layer4_relationship_behavior.under_stress
    assert parsed.layer5_boundaries.dealbreakers


def test_distill_sends_model_and_system_prompt():
    payload = json.dumps(_canned_envelope(), ensure_ascii=False)
    client = FakeAnthropic(payload)

    distill(_transcript(), {"name": "小美"}, client=client)

    call = client.last_call
    # model comes from settings; system prompt carries the builder prompts.
    assert call["model"]  # non-empty model id
    assert "persona.json" in call["system"]
    assert "language" in call["system"].lower()
    # transcript text reached the user message, Chinese preserved.
    user_content = call["messages"][0]["content"]
    assert "在干嘛呀" in user_content


def test_distill_tolerates_fenced_json():
    payload = "```json\n" + json.dumps(_canned_envelope(), ensure_ascii=False) + "\n```"
    client = FakeAnthropic(payload)
    arts = distill(_transcript(), {}, client=client)
    assert arts.parsed_persona().layer0_core.behavioral_rules


def test_distill_fills_persona_json_defaults_when_layer_missing():
    env = _canned_envelope()
    # drop a whole layer to prove the schema backfills it with defaults.
    del env["persona_json"]["layer4_relationship_behavior"]
    client = FakeAnthropic(json.dumps(env, ensure_ascii=False))
    arts = distill(_transcript(), {}, client=client)
    parsed = arts.parsed_persona()
    # missing layer is reconstructed (empty defaults), Layers 0-5 still complete.
    assert parsed.layer(4) is not None
    assert parsed.layer4_relationship_behavior.scenarios == []
