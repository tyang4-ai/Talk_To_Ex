"""Automated end-to-end smoke test of the local demo (no external accounts).

Run the app first (scripts/run-demo.ps1), then from backend/:
    .\.venv\Scripts\python.exe ..\scripts\smoke_demo.py

Drives the whole wizard over HTTP: register -> checkout(->/intake) -> create ->
upload -> distill (local) -> activate (demo) -> preview (REAL reply from the local
model on atlas). Prints each step; exits non-zero on any failure.
"""
import io
import sys
import time

import httpx

API = "http://127.0.0.1:8080/api"

CHAT = """2024-01-01 12:00 小美: 你在干嘛
2024-01-01 12:01 me: 没干嘛 你呢
2024-01-01 12:02 小美: 想你了
2024-01-02 09:00 小美: 早安 吃早饭了吗
2024-01-03 22:00 小美: 今天好累 但还是想跟你说说话
2024-01-04 20:00 小美: 在吗
2024-01-04 20:30 小美: 怎么不理我
"""


def main() -> None:
    c = httpx.Client(timeout=180)
    for _ in range(40):
        try:
            if c.get(API + "/health").json().get("ok"):
                break
        except Exception:
            time.sleep(0.5)
    else:
        sys.exit("server not up — run scripts/run-demo.ps1 first")
    print("health OK")

    email = f"demo{int(time.time())}@example.com"
    tok = c.post(API + "/auth/register", json={"email": email, "password": "pw123456"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    print("register OK ->", email)

    assert c.post(API + "/billing/checkout", headers=h, json={}).json()["url"] == "/intake"
    print("checkout -> /intake")

    intake = {"nickname": "小美", "how_you_met": "college", "time_since_breakup": "6 months",
              "personality_tags": ["clingy", "warm"], "attachment_style": "anxious"}
    pid = c.post(API + "/personas", headers=h, json={"name": "小美", "intake": intake}).json()["id"]
    print("persona id ->", pid)

    files = {"file": ("chat.txt", io.BytesIO(CHAT.encode("utf-8")), "text/plain")}
    up = c.post(f"{API}/personas/{pid}/uploads", headers=h, files=files, data={"target": "小美"}).json()
    assert up["message_count"] >= 1 and up["ex_name"] == "小美"
    print("upload ->", up["message_count"], "msgs from", up["ex_name"])

    d = c.post(f"{API}/personas/{pid}/distill", headers=h, json={}).json()
    assert d["ok"] and d["llm_model"]
    print("distill ->", d["llm_model"], f"({d['llm_model_source']})")

    a = c.post(f"{API}/personas/{pid}/activate", headers=h, json={}).json()
    assert a["e164"]
    print("activate ->", a["e164"], a["mode"])

    for msg in ["在吗 想你了", "hey, you up?"]:
        pv = c.post(f"{API}/personas/{pid}/preview", headers=h, json={"message": msg}).json()
        assert pv["bubbles"]
        print(f"preview {msg!r} -> {pv['bubbles']}")

    print("\nALL DEMO STEPS PASSED")


if __name__ == "__main__":
    main()
