"""Android SMS Backup & Restore parser — XML type 1=in/2=out + CSV fallback."""
import os

from app.ingestion.parsers import sms

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_sms_xml_counts_direction_chinese():
    msgs = sms.parse(os.path.join(FIX, "sms_backup.xml"))
    assert len(msgs) == 3
    assert msgs[0].text == "你好"
    assert msgs[0].direction == "in"     # type=1 received
    assert msgs[1].direction == "out"    # type=2 sent
    assert any("我想你了" in m.text for m in msgs)


def test_sms_csv_fallback(tmp_path):
    csv_path = tmp_path / "sms.csv"
    csv_path.write_text(
        "address,date,type,body\n"
        "+15551234567,1615582000000,1,你好\n"
        "+15551234567,1615582005000,2,hi back\n",
        encoding="utf-8",
    )
    msgs = sms.parse(str(csv_path))
    assert len(msgs) == 2
    assert msgs[0].text == "你好" and msgs[0].direction == "in"
    assert msgs[1].direction == "out"
