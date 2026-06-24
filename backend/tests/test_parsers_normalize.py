"""Normalizer + dispatch — clean_text mojibake/CJK safety, chronological sort,
bilingual emotional digest, and parse_file end-to-end routing."""
import os
from datetime import datetime, timezone

from app.ingestion import normalize
from app.ingestion.parsers.base import NormalizedMessage

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _msg(text, ts, direction="in"):
    return NormalizedMessage(sender="ex", ts=ts, text=text, direction=direction)


def test_clean_text_repairs_mojibake_keeps_cjk_and_emoji():
    mangled = "你好".encode("utf-8").decode("latin-1")  # classic IG mojibake
    assert normalize.clean_text(mangled) == "你好"
    assert normalize.clean_text("我想你了 ❤️") == "我想你了 ❤️"


def test_normalize_drops_empty_and_sorts():
    t0 = datetime(2021, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2021, 1, 2, tzinfo=timezone.utc)
    out = normalize.normalize([_msg("late", t1), _msg("   ", t1), _msg("early", t0)])
    assert [m.text for m in out] == ["early", "late"]


def test_emotional_score_bilingual():
    assert normalize.emotional_score("i still love you") >= 1
    assert normalize.emotional_score("我想你了，对不起") >= 2
    assert normalize.emotional_score("ok sounds good") == 0


def test_emotional_digest_prioritises_ex_voice():
    t = datetime(2021, 1, 1, tzinfo=timezone.utc)
    msgs = [
        _msg("我想你了", t, "in"),
        _msg("the weather is fine", t, "out"),
        _msg("i love you", t, "in"),
    ]
    digest = normalize.emotional_digest(msgs)
    texts = [m.text for m in digest]
    assert "我想你了" in texts and "i love you" in texts
    assert "the weather is fine" not in texts


def test_parse_file_routes_and_normalizes():
    t = normalize.parse_file(os.path.join(FIX, "plain_paste.txt"), target="小美")
    assert len(t) == 3
    assert t[0].text == "你好"
    # output is sorted ascending
    assert [m.ts for m in t] == sorted(m.ts for m in t)
