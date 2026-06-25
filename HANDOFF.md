# Talk_To_Ex — Continuation / Bring-up Handoff

The **infrastructure is built** (code + mock tests, all secrets are placeholders). This file is the handoff to the Claude Code agent on the machine that will actually host the local model and run the service. Start by pasting the prompt in §1.

---

## 1. Ready-to-paste prompt for the host Claude Code agent

> You are continuing the **Talk_To_Ex** project — a self-hosted SMS service where a friend subscribes (Stripe), uploads their ex's chat history, is given a phone number, and texts it to chat with a local-LLM persona of that ex. The full infrastructure is already built and pushed to this repo; **your job is to bring it live on this machine.**
>
> First read `README.md` and `docs/superpowers/specs/2026-06-24-talk-to-ex-design.md` and `docs/superpowers/plans/2026-06-24-talk-to-ex.md` so you have the full architecture. Then:
> 1. Create the backend venv and `pip install -r backend/requirements.txt`.
> 2. `cp backend/.env.example backend/.env`; generate a `FERNET_KEY` (`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`) and fill `JWT_SECRET`, `ANTHROPIC_API_KEY`, `TWILIO_*`, `STRIPE_*`. Ask me for any key you don't have.
> 3. Install Ollama, then `ollama pull qwen2.5:14b-instruct-q4_K_M` and `ollama pull bge-m3`; set `OLLAMA_NUM_PARALLEL=1` and restart Ollama.
> 4. `cd frontend && npm install && npm run build` (outputs `frontend/dist`, served by the backend).
> 5. From `backend/`, run `pytest -q` and **fix any failures** before going further (the tests are mock-based and must pass with no real keys).
> 6. Start the app: `uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips="*"` (from `backend/`). The `--proxy-headers` flag is REQUIRED so Twilio signature validation sees the public `https://ex.yang9ru.online` URL through the tunnel instead of `localhost`.
> 7. Stand up a **cloudflared named tunnel** mapping `ex.yang9ru.online → http://localhost:8080` (see `ops/cloudflared/`), and install it as a Windows service.
> 8. In Twilio, point a **trial** number's Messaging webhook (POST) at `https://ex.yang9ru.online/sms`. Verify an inbound text round-trips.
> 9. Walk **Phases 0→4** in the spec §16, then switch the number to a **paid toll-free** for the reveal.
>
> **Verified gotchas to respect (do not re-discover):** Twilio webhook must return empty TwiML immediately + send the real reply async via REST; Ollama needs explicit `num_ctx:8192` + `keep_alive:"-1"` + `OLLAMA_NUM_PARALLEL=1`; Qwen may answer as "Qwen" (test the in-character name; fix via the ChatML Modelfile in `ops/ollama/`) and code-switches (the system prompt has a language-mirror rule); iMessage `text` is NULL on iOS 16+ (decoded via `pytypedstream`); Instagram export text needs `ftfy`; WhatsApp export varies iOS/Android + `上午/下午`; WeChat decryption tooling is fragile — the plaintext-paste fallback always works. Crisis-safety is deterministic and must run before the model. **Twilio signature validation 403s behind Cloudflare unless you run uvicorn with `--proxy-headers --forwarded-allow-ips="*"`** (Twilio signs the public URL, the app otherwise sees `localhost`).
>
> Report what passes and exactly what you need from me (API keys, Twilio toll-free verification, Stripe product/price creation).

---

## 2. Manual bring-up (if you'd rather do it yourself)

```bash
# 1. Clone
git clone https://github.com/tyang4-ai/Talk_To_Ex.git && cd Talk_To_Ex

# 2. Backend
python -m venv .venv && .venv\Scripts\activate      # Windows  (mac/linux: source .venv/bin/activate)
pip install -r backend/requirements.txt

# 3. Secrets
copy backend\.env.example backend\.env              # then edit:
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"   # -> FERNET_KEY
#   fill ANTHROPIC_API_KEY, TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER, STRIPE_SECRET_KEY/WEBHOOK_SECRET/PRICE_ID/PUBLISHABLE_KEY, JWT_SECRET

# 4. Local model
ollama pull qwen2.5:14b-instruct-q4_K_M
ollama pull bge-m3
setx OLLAMA_NUM_PARALLEL 1                           # restart Ollama afterward

# 5. Frontend
cd frontend && npm install
copy .env.example .env                               # set VITE_API_URL + VITE_STRIPE_PUBLISHABLE_KEY
npm run build && cd ..

# 6. Tests + run
cd backend && pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips="*"

# 7. Tunnel (separate terminal) — see ops/cloudflared/
cloudflared service install <YOUR_TUNNEL_TOKEN>

# 8. Twilio: trial number Messaging webhook (POST) -> https://ex.yang9ru.online/sms
# 9. Stripe (test mode): create a recurring price -> STRIPE_PRICE_ID;
#    stripe listen --forward-to localhost:8080/api/stripe/webhook   (local webhook testing)
```

## 3. What's done vs what needs you
- **Done (in this repo):** all backend services (auth, billing, ingestion+parsers, distillation, conversation engine + style re-tuning, messaging + safety), the React wizard, ops configs, and mock-based tests.
- **Needs you (host-only):** real API keys, `ollama pull`, the cloudflared tunnel token, Twilio number + toll-free verification (consent = the friend's own sign-up), Stripe product/price, and a live end-to-end text.

## 4. v2 additions (the SaaS layer)
Design + plan: `docs/superpowers/{specs,plans}/2026-06-25-talk-to-ex-v2*`. Built and mock-tested (epics E10–E14, all green); E15 (frontend i18n/override/guides) + E16 docs remain.

- **Topology:** inference now runs on **atlas (Tesla T4)** over Tailscale — set `OLLAMA_BASE_URL=http://100.73.71.126:11434`; the **4090** runs the app + fine-tune training. `ollama pull qwen2.5:14b-instruct-q4_K_M` **and** `gemma3:12b` on atlas (the router picks per persona).
- **New env keys (see `backend/.env.example`):** `OLLAMA_MODEL_ZH`, `OLLAMA_MODEL_EN`, `MODEL_ROUTE_CJK_THRESHOLD`, `FREE_MESSAGE_LIMIT`, `FINETUNE_ENABLED`, `FINETUNE_TRAINER`, `TRAIN_OLLAMA_HOST`.
- **Gotcha already fixed:** Ollama needs the **integer** `keep_alive: -1`, not the string `"-1"` (string 400s).
- **Per-persona fine-tuning (host-only):** the pipeline is wired + mock-tested, but the real QLoRA train → GGUF → `ollama create` steps run on the 4090 — follow **`ops/finetune/setup.md`** and inject the runners. Until then the `finetune` job fails loudly with a host-only message (by design).
- **Proactive opener compliance:** the persona texts the friend FIRST — keep a consent record (signup + number, stored as `meta_json["peer_e164"]`/`opt_in_at`), honor STOP (Twilio + the kill-switch), and the curated opener + every generated reply pass the **outbound** safety screen.
- **Freemium:** `FREE_MESSAGE_LIMIT` (default 200) free inbound messages per persona, then the existing Stripe subscription gates replies (paywall SMS).
