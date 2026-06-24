"""Hybrid model routing — the friend's log language picks the local model.

Chinese-dominant log -> Qwen; English-dominant -> Gemma. Pure functions, no
network, no keys. Mixed zh/en throughout (the real-world case)."""
from __future__ import annotations

from app.config import settings
from app.convo import model_router as mr


def test_cjk_ratio_pure_and_mixed():
    assert mr.cjk_ratio("你好世界") == 1.0
    assert mr.cjk_ratio("hello world") == 0.0
    assert mr.cjk_ratio("") == 0.0
    # digits/punctuation/emoji are ignored — only letters vs hanzi count.
    assert mr.cjk_ratio("123 !!! 😊") == 0.0
    assert mr.cjk_ratio("你好 hi") == 0.5  # 2 hanzi, 2 latin


def test_chinese_dominant_routes_qwen():
    msgs = [{"text": "你好呀"}, {"text": "在干嘛"}, {"text": "想你了"}, {"text": "ok"}]
    assert mr.detect_dominant_language(msgs) == "zh"
    lang, model = mr.pick_model(msgs)
    assert lang == "zh"
    assert model == settings.ollama_model_zh


def test_english_dominant_routes_gemma():
    msgs = [{"text": "hey you up"}, {"text": "miss you lol"}, {"text": "我"}]
    assert mr.detect_dominant_language(msgs) == "en"
    lang, model = mr.pick_model(msgs)
    assert lang == "en"
    assert model == settings.ollama_model_en


def test_accepts_str_dict_body_and_empty():
    assert mr.detect_dominant_language([]) == "en"          # scriptless -> en fallback
    assert mr.detect_dominant_language(["你好世界 你好世界"]) == "zh"  # raw strings
    assert mr.detect_dominant_language([{"body": "hello there friend"}]) == "en"  # 'body' key


def test_threshold_is_configurable(monkeypatch):
    msgs = [{"text": "你好 hi"}]  # ratio == 0.5
    monkeypatch.setattr(settings, "model_route_cjk_threshold", 0.9)
    assert mr.detect_dominant_language(msgs) == "en"
    monkeypatch.setattr(settings, "model_route_cjk_threshold", 0.1)
    assert mr.detect_dominant_language(msgs) == "zh"
