"""iMessage parser — sms.db join, attributedBody NULL-text fallback (injected
decoder), per-row ns/sec date branching, is_from_me → direction."""
import os
from datetime import datetime, timezone

from app.ingestion.parsers import imessage
from app.ingestion.parsers.imessage import apple_date_to_datetime

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
DB = os.path.join(FIX, "sms.db")


def _fake_decoder(blob):
    # stands in for pytypedstream decoding of the attributedBody typedstream
    return "我爱你" if blob else ""


def test_imessage_counts_and_text_rows():
    msgs = imessage.parse(DB, decode_attributed_body=_fake_decoder)
    assert len(msgs) == 3
    assert msgs[0].text == "你好"          # plain text row, Chinese
    assert msgs[0].direction == "in"        # is_from_me=0
    assert msgs[1].direction == "out"       # is_from_me=1


def test_imessage_attributedbody_fallback():
    msgs = imessage.parse(DB, decode_attributed_body=_fake_decoder)
    # the NULL-text row is recovered via the injected attributedBody decoder
    assert msgs[-1].text == "我爱你"
    assert msgs[-1].direction == "in"


def test_imessage_date_magnitude_branch():
    # nanoseconds since 2001 and seconds since 2001 both land on the same instant
    ns = 600_000_000 * 1_000_000_000
    s = 600_000_000
    assert apple_date_to_datetime(ns) == apple_date_to_datetime(s)
    # sanity: 600M seconds after 2001-01-01 is in 2020
    assert apple_date_to_datetime(s).astimezone(timezone.utc).year == 2020


def test_imessage_null_decoder_default_skips_when_lib_absent():
    # With the real (lazy) decoder and no pytypedstream installed, the NULL-text
    # row decodes to "" and is skipped — proving the import is not load-bearing.
    msgs = imessage.parse(DB)  # default decoder
    assert all(m.text for m in msgs)  # no empty bodies leak through
    assert len(msgs) in (2, 3)        # 2 if lib absent, 3 if installed
