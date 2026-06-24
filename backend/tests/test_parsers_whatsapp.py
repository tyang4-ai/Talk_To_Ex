"""WhatsApp parser — iOS + Android, U+200E strip, continuation merge, media
drop, Chinese 上午/下午 locale."""
import os

from app.ingestion.parsers import whatsapp

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_whatsapp_ios_counts_and_continuation():
    msgs = whatsapp.parse(os.path.join(FIX, "whatsapp_ios_chat.txt"), target="Xiao Mei")
    # system encryption line + <Media omitted> dropped → 3 real messages
    assert len(msgs) == 3
    # continuation line merged into the prior message body
    assert msgs[1].text == "hey\nthis wraps onto a second line"


def test_whatsapp_ios_chinese_and_direction():
    msgs = whatsapp.parse(os.path.join(FIX, "whatsapp_ios_chat.txt"), target="Xiao Mei")
    assert msgs[0].text == "你好"
    assert msgs[0].direction == "in"
    assert any(m.text == "我想你了" for m in msgs)
    assert all("Media omitted" not in m.text for m in msgs)


def test_whatsapp_android_zh_ampm():
    msgs = whatsapp.parse(os.path.join(FIX, "whatsapp_android_chat.txt"), target="Xiao Mei")
    # 下午9:06 line must parse as a real message (not be dropped)
    assert any(m.text == "我想你了" for m in msgs)
    assert msgs[0].direction == "in"
    assert any(m.direction == "out" for m in msgs)
