"""WeChat parser — best-effort plaintext export, media-tag stripping, and
ParserNeedsManualExport on an encrypted DB."""
import os

import pytest

from app.ingestion.parsers import wechat
from app.ingestion.parsers.base import ParserNeedsManualExport

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_wechat_text_export_counts_and_chinese():
    msgs = wechat.parse(os.path.join(FIX, "wechat_export.txt"), target="小美")
    # [图片] media-only line stripped → 3 real messages
    assert len(msgs) == 3
    assert msgs[0].text == "你好呀"
    assert msgs[0].direction == "in"
    assert any(m.text == "我想你了" for m in msgs)
    assert all("[" not in m.text for m in msgs)  # media tags removed


def test_wechat_encrypted_db_raises_manual_export():
    with pytest.raises(ParserNeedsManualExport):
        wechat.parse(os.path.join(FIX, "wechat_encrypted.db"))


def test_wechat_html_export(tmp_path):
    html = tmp_path / "chat.html"
    html.write_text(
        "<html><body>"
        "<div>2021-03-12 21:04:33 小美: 在吗</div>"
        "<div>2021-03-12 21:05:00 我: 在的</div>"
        "</body></html>",
        encoding="utf-8",
    )
    msgs = wechat.parse(str(html), target="小美")
    assert len(msgs) == 2
    assert msgs[0].text == "在吗" and msgs[0].direction == "in"
    assert msgs[1].direction == "out"
