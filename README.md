# Talk_To_Ex

A self-hosted, single-operator SMS service: a friend signs up on a small website,
**subscribes via Stripe**, uploads their own chat history with an ex, is assigned a
phone number, and **texts it** — a local LLM replies in the voice of that ex,
distilled from the real chat logs.

It's a personal closure/"gag" tool, not a commercial product. The friend operates
it on **their own** relationship data and texts the persona **themselves** — no
uninvolved third party is deceived. A deterministic, bilingual (Chinese + English)
crisis-safety layer runs **before** the model and is non-negotiable, because this is
emotionally sensitive territory.

> Full design: [`docs/superpowers/specs/2026-06-24-talk-to-ex-design.md`](docs/superpowers/specs/2026-06-24-talk-to-ex-design.md).
> Implementation plan: [`docs/superpowers/plans/2026-06-24-talk-to-ex.md`](docs/superpowers/plans/2026-06-24-talk-to-ex.md).

---

## How it works

- **One FastAPI monolith** (`localhost:8080`) serves a polished React SPA **and** the
  REST API. SQLite via SQLModel; sensitive data Fernet-encrypted at rest.
- **Hybrid AI.** The **Claude API** distills the persona from chat logs **once**
  (offline), and re-tunes only the *voice/expression* every ~100 messages. A
  **local Ollama / Qwen2.5-14B** model answers every live text — chat data never
  leaves the box for inference.
- **Twilio toll-free SMS.** The inbound webhook returns an empty `<Response/>`
  immediately, then sends the real reply **asynchronously** via the Twilio REST API
  (local inference is too slow for the ~15 s webhook timeout).
- **Cloudflare named tunnel** exposes only the app at `ex.yang9ru.online` →
  `localhost:8080`. **Ollama (`:11434`) is never tunnelled.**
- **Stripe Checkout subscription** — the friend pays; payment gates number
  provisioning, persona activation, and replies.

### Architecture

```
Friend's phone ──SMS──▶ Twilio (toll-free) ──webhook POST──▶ Cloudflare named tunnel
                                                                  │  ex.yang9ru.online → localhost:8080
                                                                  ▼
 ┌──────────────────────────── Talk_To_Ex (FastAPI, localhost:8080) ───────────────────────────┐
 │  Static React portal  │  Auth  │  Billing(Stripe)  │  Ingestion→Distill(Claude)             │
 │  Messaging gateway (Twilio webhook + sender)  │  Conversation engine  │  Safety layer         │
 │  Persona store  │  SQLite + Fernet-encrypted files                                            │
 └───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                  ▼
                              Ollama (localhost:11434) — qwen2.5:14b + bge-m3   [NEVER tunnelled]
```

Single process, single SQLite DB, single tunnel. Ollama bound to localhost only.

---

## Try it locally — demo mode (no external accounts)

Run the **whole website** on `localhost:8080` with **zero** API keys. `DEMO_MODE`
swaps the paid externals for local fallbacks (heuristic persona distillation
instead of Claude; Stripe + Twilio bypassed), while the in-browser persona chat
uses the **real local model** (Ollama, `OLLAMA_BASE_URL` → atlas by default).

```powershell
# one command — builds the SPA if needed, serves SPA+API in demo mode
.\scripts\run-demo.ps1
# then open http://localhost:8080 and click through:
#   register → choose plan → 3 questions → upload a chat log → build → reveal → chat
```

Verify it headlessly (whole flow incl. a real model reply):
```powershell
cd backend; .\.venv\Scripts\python.exe ..\scripts\smoke_demo.py
```

What works in demo: the entire wizard + **live in-browser chat with the persona**.
What still needs real keys (live only): **SMS** (Twilio), **real billing** (Stripe),
and the public **Cloudflare tunnel**. Set `DEMO_MODE=false` and fill `backend/.env`
to go live.

---

## v2 — SaaS layer (in progress)

Beyond the v1 scaffold above, the project is growing into a small real-feeling
SaaS. Full design: [`docs/superpowers/specs/2026-06-25-talk-to-ex-v2-design.md`](docs/superpowers/specs/2026-06-25-talk-to-ex-v2-design.md);
plan (epics E10–E16): [`docs/superpowers/plans/2026-06-25-talk-to-ex-v2.md`](docs/superpowers/plans/2026-06-25-talk-to-ex-v2.md).

| Feature | Status |
|---|---|
| **Hybrid model routing** — log language picks the local model (zh→Qwen, en→Gemma), user-overridable | ✅ backend (`app/convo/model_router.py`, `POST /api/personas/{id}/model`) |
| **Freemium metering** — `FREE_MESSAGE_LIMIT` free messages, then a Stripe subscription (paywall SMS) | ✅ backend (`app/billing/metering.py`) |
| **Async job queue** — persisted `Job` queue + worker for long out-of-process work | ✅ backend (`app/jobs/`) |
| **Per-persona fine-tuning** — QLoRA voice adapter, served as a `persona-<id>` Ollama model | ✅ orchestration mock-tested (`app/finetune/`); ⚠️ real training is host-only → [`ops/finetune/setup.md`](ops/finetune/setup.md) |
| **The "reveal"** — on training-done the persona texts the friend FIRST with a curated apology opener; outbound safety screen | ✅ backend (`app/messaging/{reveal,opener}.py`, `safety.screen_outbound`) |
| **Portal i18n (zh/en) + guided-upload screenshots + model-override UI** | ⏳ frontend (E15) |

**Topology change (v2):** inference runs on **atlas (Tesla T4)** over Tailscale
(`OLLAMA_BASE_URL=http://100.73.71.126:11434`); the **RTX 4090** runs the app and
the fine-tune training jobs. Ollama stays on the private tailnet — never tunnelled.

---

## Repo layout

```
Talk_To_Ex/
  backend/
    app/
      main.py            # FastAPI app: lifespan (create tables), /api/health, router includes, SPA mount
      config.py          # typed settings (pydantic-settings); secrets default to "" and fail at the boundary
      db.py              # SQLModel engine + all table models (spec §7)
      crypto.py          # Fernet encrypt/decrypt + enc_str/dec_str helpers
      auth/              # JWT register/login + get_current_user
      billing/           # Stripe checkout, webhook, number provisioning
      ingestion/         # upload + normalize + parsers/ (imessage, instagram, whatsapp, wechat, sms, plaintext)
      distill/           # Claude distillation pipeline + vendored ex-skill prompts
      persona/           # encrypted artifact store + embeddings + routes
      convo/             # conversation engine, history, summary, ollama_client, style_tuner
      messaging/         # twilio_webhook, sender, safety, crisis_words
    tests/               # mock-based pytest suite (no network, no real keys)
    requirements.txt
    .env.example         # copy to backend/.env and fill in
    pytest.ini
  frontend/              # Vite + React 18 + TS + Tailwind wizard (Tinder-vibe). Built to frontend/dist/
  ops/
    ollama/              # Modelfile + setup.md (pull models, NUM_PARALLEL, keep_alive)
    cloudflared/         # config.example.yml + windows-service.md
  docs/superpowers/      # spec + plan
  README.md
  .gitignore
```

> The backend serves the SPA from `frontend/dist/` **if that folder exists**
> (`app/main.py` mounts it). In dev you can instead run Vite separately and point
> it at the API.

---

## Prerequisites

- **Python 3.11+**
- **Node 18+** (for the frontend wizard)
- **Ollama** (Windows) with `qwen2.5:14b-instruct-q4_K_M` + `bge-m3` pulled —
  see [`ops/ollama/setup.md`](ops/ollama/setup.md). Plan for ~16 GB VRAM.
- **cloudflared** for the public tunnel — see
  [`ops/cloudflared/windows-service.md`](ops/cloudflared/windows-service.md).
- Accounts/keys (placeholders are fine until the live phases): **Anthropic** (Claude),
  **Twilio** (toll-free SMS), **Stripe** (Checkout subscription), a **Cloudflare**
  tunnel for `ex.yang9ru.online`.

All secrets are read from `backend/.env`; nothing is hardcoded. The app imports and
the mock test suite passes **without** real keys — a missing secret only raises when
the real client is actually invoked.

---

## Quickstart (local dev)

### Backend

```bash
cd backend
python -m venv .venv

# activate the venv:
#   Windows PowerShell:  .\.venv\Scripts\Activate.ps1
#   Git Bash:            source .venv/Scripts/activate
#   macOS/Linux:         source .venv/bin/activate

pip install -r requirements.txt

# config: copy the example and fill in keys (placeholders work for the mock tests)
cp .env.example .env
# generate a real FERNET_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# run the API (creates the SQLite tables on startup via the lifespan hook)
uvicorn app.main:app --reload --port 8080
```

Check it's up: `curl http://localhost:8080/api/health` → `{"ok":true}`.

### Tests (mock-based — no network, no real keys)

```bash
cd backend
pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server (proxy /api → http://localhost:8080)
npm run build    # emits frontend/dist/ — the backend then serves it at /
```

After `npm run build`, restart the backend; `app/main.py` will mount
`frontend/dist/` at `/`, so the whole product is served from one origin
(`localhost:8080`) — trivial auth/CORS.

### Local model

Pull the models and apply the required Ollama settings (`OLLAMA_NUM_PARALLEL=1`,
custom Modelfile) per [`ops/ollama/setup.md`](ops/ollama/setup.md). The app talks to
Ollama at `OLLAMA_BASE_URL` (default `http://localhost:11434`).

---

## Bring-up order (Phases 0 → 4)

This repo is the **infrastructure scaffold** — complete code with placeholder
secrets and mock-based tests. Standing it up against live services follows this
order (spec §16). Each phase is independently testable; don't skip ahead.

- **Phase 0 — Pipe.** Install deps, fill `backend/.env`, `ollama pull` both models,
  start the cloudflared tunnel to `ex.yang9ru.online`, and point a Twilio **trial**
  number's webhook at `https://ex.yang9ru.online/sms`. Goal: an inbound text hits the
  webhook and a **hardcoded** reply comes back. Proves the SMS ↔ tunnel ↔ app pipe.

- **Phase 1 — Brain (MVP).** Real Ollama replies from a **hand-written** persona;
  per-phone history + bubble-split + the deterministic crisis-safety tripwire.
  **← At this point you can text the number and get in-character replies.**

- **Phase 2 — Ingestion + distillation.** Guided upload (start with
  WhatsApp/plaintext, then iMessage, Instagram, then best-effort WeChat) → Claude
  distill → a real encrypted persona + memories, with a parse preview.

- **Phase 3 — Portal + billing.** The Tinder-style wizard live; Stripe **test-mode**
  product + signed webhook driving subscription state; encryption-at-rest verified
  end-to-end.

- **Phase 4 — Reveal.** Corrections/versioning, upgrade Twilio to a **paid toll-free**
  number (trial messages carry a watermark), operator dashboard + kill-switch, and
  the real Stripe price.

> Verified gotchas to remember at bring-up (details inline in `ops/` and the spec):
> iMessage `text` is NULL on iOS 16+ (decode `attributedBody` with `pytypedstream`,
> per-row ns/sec date branching); Instagram exports are newest-first and need
> `ftfy` mojibake repair; always set Ollama `num_ctx` explicitly (default is 4K);
> toll-free SMS is consent-gated (the friend's own sign-up is the opt-in).

---

## Safety & privacy (non-negotiable)

- **Crisis tripwire** runs deterministically **before** the model, in both Chinese
  and English. On a hit it bypasses the persona entirely, replies with **988** + a
  local hotline, logs a `safety_events` row, and alerts the operator. The model's
  own refusal is never relied on.
- **Kill-switch:** a per-number flag and a global `KILL_SWITCH` env var silence all
  replies instantly.
- **Encryption at rest:** all chat data + persona artifacts are Fernet-encrypted
  (`FERNET_KEY`). Nothing leaves the box except the one-time Claude distillation
  call (disclosed to the friend in the wizard). Ollama is localhost-only and never
  tunnelled.
