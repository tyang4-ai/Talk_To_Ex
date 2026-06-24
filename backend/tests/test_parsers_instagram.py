"""Instagram parser — mojibake repair, ascending timestamp sort, schema keys."""
import os

from app.ingestion.parsers import instagram

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
IG_DIR = os.path.join(FIX, "instagram")


def test_instagram_counts_and_order():
    msgs = instagram.parse(IG_DIR, target="小美")
    assert len(msgs) == 4
    # paginated across message_1/message_2, newest-first → must end up ascending
    tss = [m.ts for m in msgs]
    assert tss == sorted(tss)


def test_instagram_mojibake_repaired_and_chinese():
    msgs = instagram.parse(IG_DIR, target="小美")
    first = msgs[0]
    # mojibake (UTF-8-as-latin1) repaired by ftfy, emoji intact
    assert first.text == "你好呀 😊"
    assert first.sender == "小美"
    assert any("我想你了" in m.text and "❤️" in m.text for m in msgs)


def test_instagram_direction_by_target():
    msgs = instagram.parse(IG_DIR, target="小美")
    assert msgs[0].direction == "in"   # from the ex
    assert any(m.direction == "out" for m in msgs)  # owner's replies
