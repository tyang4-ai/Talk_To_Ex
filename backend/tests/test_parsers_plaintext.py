"""Plaintext / PDF fallback parser — dated header regex + raw-blob fallback."""
import os

from app.ingestion.parsers import plaintext

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_plaintext_dated_lines():
    msgs = plaintext.parse(os.path.join(FIX, "plain_paste.txt"), target="小美")
    assert len(msgs) == 3
    assert msgs[0].text == "你好" and msgs[0].direction == "in"
    assert msgs[1].direction == "out"
    assert any(m.text == "我想你了" for m in msgs)


def test_plaintext_raw_blob_fallback(tmp_path):
    p = tmp_path / "paste.txt"
    p.write_text("我喜欢你\nbut it's complicated\n\n真的吗", encoding="utf-8")
    msgs = plaintext.parse(str(p), target="ex")
    # no dated headers → every non-empty line kept as an inbound message
    assert len(msgs) == 3
    assert all(m.direction == "in" for m in msgs)
    assert msgs[0].text == "我喜欢你"
