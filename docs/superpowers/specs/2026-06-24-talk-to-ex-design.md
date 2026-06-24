# Talk_To_Ex — Design Spec

- **Date:** 2026-06-24
- **Status:** Draft for review
- **Repo (target):** `github.com/tyang4-ai/Talk_To_Ex` (currently empty — scaffolded fresh)
- **Reference project:** `github.com/perkfly/ex-skill` (MIT) — we vendor its distillation prompts, 5-layer persona schema, and chat parsers. We do **not** reuse the `yang9ru/megrez` codebase (deprecated per owner).

---

## 0. What this is

A self-hosted, single-operator service that lets a friend talk by SMS to an AI mimicking their ex, distilled from real chat history. It's a personal "gag"/closure tool, not a commercial product. The friend sets everything up themselves through a website, **subscribes (pays) via Stripe**, is assigned a phone number, and texts it; a local LLM replies in the ex's voice.

**Consent / ethics framing (load-bearing, not decoration):**
- The friend operates the tool on **their own** relationship data and texts the persona **themselves** — there is no deception of an uninvolved third party. This mirrors the original `ex-skill` use case ("distill memories to remember, not to win them back"), delivered over SMS.
- The friend's own sign-up + first outbound text is the **documented opt-in/consent** required for Twilio toll-free verification.
- A deterministic crisis-safety layer (see §12) is mandatory because this is emotionally sensitive (grief, breakups). It is non-negotiable and built in from Phase 1.

---

## 1. Locked decisions

| Area | Decision |
|---|---|
| Product shape | Self-hosted single-box app; one operator (you), N friends (≈1) |
| Channel | Real SMS via **Twilio toll-free** (build on free trial → paid toll-free ~$2.15/mo for the reveal) |
| Public ingress | **Cloudflare named tunnel** (Windows service) → `ex.yang9ru.online` → `localhost:8080` |
| AI hosting | **Hybrid:** Claude API distills persona once (offline); local **Ollama / Qwen2.5-14B** answers live texts |
| Ingestion | Pluggable parsers: iMessage/SMS, Instagram, WhatsApp, WeChat (best-effort) + plaintext/PDF fallback |
| Language | Mixed Chinese/English |
| Billing | **Stripe Checkout subscription — the friend pays**; payment gates number provisioning/activation |
| Architecture | **A — lean greenfield monolith**, best-for-task libraries (no megrez code) |
| Web portal | **Polished, Tinder-style** dating-app aesthetic (warm gradient, cards, bold type, playful microcopy) |
| Data import | **Guided per-platform export wizard** (screenshots + auto-detect + parse preview). **No OAuth auto-pull** — platforms don't expose personal DM history |
| Style adaptation | **Re-tune the voice every ~100 messages** via Claude — adjusts *expression/style only*; core personality frozen |
| This session's deliverable | Full code/infrastructure with **placeholder secrets**; mocked tests; pushed to `Talk_To_Ex`; + a continuation prompt |

---

## 2. Tech stack (greenfield, best-for-task)

**Backend** — Python 3.11+, **FastAPI** (async), **SQLModel** (SQLAlchemy 2.0 + Pydantic v2) over **SQLite**, `uvicorn`. Auth: **PyJWT** + **passlib[bcrypt]** (slim, custom — no Google OAuth). Uploads: FastAPI `UploadFile` + `aiofiles`. Crypto: `cryptography` (Fernet) for at-rest encryption of chat data + artifacts. HTTP: `httpx`. Async reply work: FastAPI `BackgroundTasks` / `asyncio` (no Redis/Celery — overkill at this scale).

**External SDKs** — `anthropic` (distillation), `twilio` (SMS), `stripe` (billing). **Local model** via Ollama HTTP API (`httpx`), models `qwen2.5:14b-instruct-q4_K_M` (chat) + `bge-m3` (embeddings, optional RAG).

**Frontend** — **Vite + React 18 + TypeScript + Tailwind**, `react-router-dom`, `axios`, `@stripe/stripe-js` (Checkout redirect), `framer-motion` (card/swipe motion). A multi-step wizard SPA served as static files by the same FastAPI app (one origin → trivial auth/CORS).

**Visual direction — "Tinder for your ex"** (polished, intentional; built with the `frontend-design` skill at build time): a warm dating-app aesthetic — Tinder-style **vertical gradient** (coral→pink/`#FD297B→#FF5864→#FF655B`), full-bleed **swipeable cards**, large rounded avatars, bold tight display type (e.g. Poppins/`Inter` display) over a soft neutral background, round pill CTAs, subtle motion on transitions, and playful, knowing microcopy ("Swipe right on your ex 💔", "It's a match… sort of"). The setup flow is framed as building a *profile/match*, and the live chat preview mimics a dating-app message thread. Mobile-first, since the friend will be on their phone.

**Ops** — `cloudflared` (Cloudflare Tunnel, Windows service); Ollama (Windows). Both documented in `ops/`, configured by env, not hardcoded.

---

## 3. Architecture & topology

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

## 4. Components (each an isolated unit: purpose / interface / depends-on)

1. **Auth** — slim JWT email/password. *IF:* `POST /api/auth/{register,login}` → JWT; `get_current_user` dependency. *Dep:* PyJWT, passlib, DB.
2. **Billing (Stripe)** — subscription gate. *IF:* `POST /api/billing/checkout` → Checkout session URL; `POST /api/stripe/webhook` (signed) → sets subscription active/canceled. *Dep:* stripe SDK, DB.
3. **Ingestion** — upload + parse. *IF:* `POST /api/personas/{id}/uploads` (multipart) → stored encrypted + normalized transcript `[{sender, ts, text, direction}]`. *Dep:* parsers, aiofiles, crypto.
4. **Parsers** (`ingestion/parsers/*`) — one per format, each: `parse(path) -> NormalizedTranscript`. Pure, independently testable. *Dep:* stdlib + (`pytypedstream`, `ftfy`, `chat-miner`, WeChat tooling).
5. **Distillation** — transcript + intake → `persona.md` + `memories.md` + `meta.json` via Claude using vendored `ex-skill` prompts. *IF:* `distill(persona_id) -> artifacts`. *Dep:* anthropic SDK, prompts.
6. **Persona store** — encrypted artifact CRUD + optional `bge-m3` embeddings. *IF:* `load(persona_id)`, `save(...)`, `versions(...)`. *Dep:* crypto, DB, Ollama embed.
7. **Conversation engine** — `reply(persona_id, peer_e164, body) -> [bubbles]`: builds prompt (persona system + few-shot SMS style + language-mirror rule) from persona + memories + per-phone history + rolling summary; calls Ollama; splits bubbles; re-summarizes every ~25 msgs. *Dep:* Ollama client, persona store, DB.
8. **Messaging gateway** — `messaging/twilio_webhook.py` (verify signature → safety → empty TwiML ack → BackgroundTask) + `sender.py` (Twilio REST, multi-bubble, 1–3 s delay). *Dep:* twilio SDK, safety, engine.
9. **Safety layer** — `safety.py`: deterministic bilingual crisis tripwire run **before** the engine; static hotline reply + operator alert + `safety_events` log; per-number kill-switch; rate caps. *Dep:* DB, sender.
10. **Ops adapters** — `convo/ollama_client.py` (configurable base URL/model), `ops/cloudflared/`, `ops/ollama/` (Modelfile + setup notes).

---

## 5. Billing (Stripe) — the friend pays

- **Model:** Stripe **Checkout in `subscription` mode**, one recurring price (placeholder `STRIPE_PRICE_ID`, e.g. a "Reconnect" plan) priced to comfortably cover the toll-free number.
- **Flow:** wizard "Choose your plan" → `POST /api/billing/checkout` creates a Checkout Session (`success_url`/`cancel_url` back to the wizard) → friend pays on Stripe → Stripe fires `checkout.session.completed` (and later `invoice.paid` / `customer.subscription.deleted`) to `POST /api/stripe/webhook` (verified with `STRIPE_WEBHOOK_SECRET`) → we mark the user's subscription **active** and unlock **number provisioning + activation**.
- **Gating:** persona activation and SMS replies are refused unless `subscription_status == active`.
- **Number provisioning:** on activation, a `NumberService` either (a) returns the configured dev/trial number (`TWILIO_FROM_NUMBER` env) or (b) auto-buys a toll-free number via Twilio API (production path; written but behind a flag). Assignment recorded in `numbers`.
- **All Stripe keys are placeholders**; built/tested against Stripe **test mode** + mocked webhook events.

---

## 6. Data flows

**Setup:** sign up → **Stripe Checkout (pay)** → webhook marks active → number assigned → upload export(s) → 3-question intake → parse → Claude distill → encrypted persona/memories → preview-chat → **Activate**.

**Live text:** friend texts the number → Twilio `POST` webhook → **signature check** → **safety tripwire** → safe? enqueue (BackgroundTask) + return empty `<Response/>` ack → engine builds prompt from persona + memories + history + summary → Ollama → split bubbles → Twilio REST sends each with delay → persist turns → maybe re-summarize.

**Payment lifecycle:** `invoice.paid` keeps active; `customer.subscription.deleted`/past_due → deactivate replies (persona dormant, data retained).

---

## 7. Data model (SQLModel / SQLite)

- `users`(id, email, pw_hash, stripe_customer_id, subscription_status, subscription_id, created_at)
- `personas`(id, user_id, slug, name, meta_json, persona_md_enc, memories_md_enc, **style_overlay_enc** [latest Layer-2 refinement], status[draft|active|dormant], created_at, updated_at)
- `style_tunings`(id, persona_id, conversation_id, overlay_json_enc, msg_count_at_run, created_at) — history of voice re-tunes (§9.1)
- `numbers`(id, persona_id, e164, provider, mode[trial|tollfree], status)
- `conversations`(id, persona_id, peer_e164, summary, last_active)
- `messages`(id, conversation_id, direction[in|out], body, ts)
- `memory_chunks`(id, persona_id, text, embedding_json) — optional RAG
- `uploads`(id, persona_id, filename, format, raw_enc_path, normalized_enc_path, created_at)
- `corrections`(id, persona_id, instruction, applied_at)
- `versions`(id, persona_id, snapshot_json, created_at) — `ex-skill` version_manager pattern (keep last 10)
- `safety_events`(id, conversation_id, kind, body, ts)

Sensitive blobs (`*_md_enc`, `*_enc_path` contents) are Fernet-encrypted with `FERNET_KEY`.

---

## 8. Messaging gateway — verified Twilio specifics

- Inbound webhook is **`application/x-www-form-urlencoded` POST**; key fields `From`, `To`, `Body`, `MessageSid`. Verify `X-Twilio-Signature` (Twilio SDK `RequestValidator`).
- **Reply pattern:** return an **empty `<Response/>` TwiML immediately** (well under Twilio's ~15 s webhook timeout), then send the real reply **asynchronously via REST `Messages.create`**. Never generate synchronously (local Ollama is too slow for the timeout).
- **Numbers:** US **toll-free**. Unregistered 10-digit long codes are hard-blocked by US carriers (since 2025) — do **not** use a bare long code. Free **trial** works for dev to verified numbers but prepends a "Sent from a Twilio trial account" watermark → upgrade to **paid toll-free** before the reveal. Toll-free verification is free but **consent-gated** (satisfied by the friend's own sign-up/opt-in). Have Privacy Policy + Terms URLs ready (Twilio requires them for new TF verifications by Sep 2026).

---

## 9. Conversation engine — verified Ollama/Qwen specifics

- Endpoint `POST http://localhost:11434/api/chat`, `messages:[{role,content}]`, `stream:false`, `options:{num_ctx:8192, temperature:0.8}`, `keep_alive:"-1"` (stay resident).
- Also set env `OLLAMA_NUM_PARALLEL=1` (KV-cache = `num_ctx × NUM_PARALLEL`; the VRAM-tiering ignores parallelism). Default `num_ctx` is only 4K below 24 GiB — **always set it explicitly**.
- Model `qwen2.5:14b-instruct-q4_K_M` (9.0 GB; fits 16 GB+ with headroom). `qwen3:14b` is a viable upgrade but needs think-mode suppression (`/no_think`) — out of scope for the scaffold; env-swappable.
- **Code-switching control:** Qwen leaks languages; add an explicit system rule "reply in the same language the user just used" + the persona's own style examples.
- **Persona-name leak:** Qwen may answer as "Qwen" ignoring the system persona (Ollama #6873); mitigate via a custom Modelfile (ChatML) and restating the persona/name in the first user-turn wrapper. Smoke-test the in-character name before shipping.
- **Memory:** at 1 user, **stuff** distilled memories + rolling summary + last ~15–20 raw turns into context; add `bge-m3` top-k RAG only if memories outgrow the budget. Raw turns persisted at full fidelity (summaries are derived, never source of truth).
- **SMS style:** few-shot exchanges (lowercase, fragmentary, short, code-switching); model emits a bubble delimiter; app splits and sends each as a separate Twilio message with a randomized 1–3 s delay.

### 9.1 Periodic style re-tuning (every ~100 messages)

To make the persona feel *alive* — picking up the rhythm, vocabulary, and in-jokes of the ongoing conversation — a **style tuner** (`convo/style_tuner.py`) runs every `STYLE_RETUNE_EVERY` messages (default **100**, per conversation), as the **second** use of the Claude API (after initial distillation).

- **Input:** the **immutable original persona** (Layers 0–5, frozen from distillation) + the current style overlay + the last ~100 turns of *this* conversation + `meta.json`.
- **Output:** an updated **style overlay** — a refinement of **Layer 2 (expression/style) only**: vocabulary, sentence length, emoji/punctuation habits, cadence, current shared references. Stored encrypted, versioned in `style_tunings`.
- **Hard guardrail against drift:** the tuner prompt is explicitly forbidden from altering Layer 0 (core personality), 1 (identity), 3 (emotional logic), 4 (relationship behavior), or 5 (boundaries). A post-step validation diffs the returned core layers against the frozen original and **rejects** the overlay if any core layer changed. User corrections (`correction_handler`) always override the overlay.
- **Live assembly:** every reply prompt = frozen persona (0,1,3,4,5) + **latest style overlay** (2) + rolling summary + recent turns. So the *personality* is constant; only the *voice* adapts.
- **Cost:** ~1 Claude call per 100 messages — negligible. Runs in a BackgroundTask; never blocks a reply.

---

## 10. Ingestion & parsers — verified per-format specifics

- **iMessage/SMS (Apple)** — works on Windows with **no Mac**: friend backs up their iPhone **unencrypted** via the Apple Devices app → read `sms.db` (Manifest hash `3d0d7e5fb2ce288813306e4d4636395e047a3d28`) as plain SQLite. Schema `message`/`handle`/`chat`/`chat_message_join`. **`message.text` is NULL on iOS 16+** → decode `attributedBody` typedstream with **`pytypedstream`** (never naive byte-slicing — corrupts CJK). `date` = ns since 2001-01-01 (`/1e9 + 978307200`); **branch per-row by magnitude** (iOS 16+ mixes ns/seconds). Set "Keep Messages = Forever" before backup. Filter `is_from_me=0` for the ex's voice.
- **Instagram DMs** — JSON "Download Your Information": glob `**/messages/inbox/*/message_*.json`, concat `messages[]`, **sort ascending by `timestamp_ms`** (export is newest-first + paginated). **Mojibake fix** per text field: prefer `ftfy.fix_text(s)` (the bare `s.encode('latin-1').decode('utf-8')` throws on already-valid text). Handle both old (`conversation/sender/text`) and new (`messages/sender_name/content`) schemas.
- **WhatsApp** — "Export chat (without media)" `_chat.txt`. Reuse **`joweich/chat-miner`** (MIT) — handles iOS `[DD/MM/YY, HH:MM:SS] Sender:` vs Android `M/D/YY, H:MM AM - Sender:`, U+200E/BOM, multiline, system lines, day-first inference. Chinese locale emits `上午/下午` → pre-normalize or re-export English/24h.
- **WeChat (best-effort)** — PC 4.x SQLCipher-4 decryption is the primary path on a Windows host with WeChat installed (DB at `xwechat_files/.../message_N.db`, key in process memory while logged in). Tooling is **fragile** (PyWxDump/wx_key/wechat-dump-rs all had 2025–26 takedowns/breakage) → vendor + pin **one** self-contained extractor, test against the installed build day one, and **always offer a plaintext-paste fallback**. Quoted/card messages need `lz4.block` + protobuf decode. Treated as best-effort, never a hard dependency.
- **Plaintext / PDF** — always-works fallback (`pdfminer.six` / plain text), reuses `ex-skill`'s regex digesting.
- **Normalizer** — all parsers emit the same `NormalizedTranscript`; `ex-skill`'s `sms_parser.py`/`wechat_parser.py` emotional-keyword digesting (bilingual) reused to weight the distillation input.

### 10.1 Guided export wizard (smooth manual import — no OAuth)

OAuth auto-obtain is **not possible**: Instagram's Basic Display API was retired (Dec 2024) and its Messaging API only serves business→customer replies; WhatsApp/WeChat expose business APIs only; iMessage has no API. None return a user's personal message history, and scraping/automating the export would violate ToS and break constantly. So we make the **sanctioned manual export effortless**:

- **Per-platform step-by-step guides** in the wizard (`frontend/src/pages/import/*`), each with numbered steps + screenshots/GIFs:
  - *Instagram:* Settings → Accounts Center → Your information and permissions → **Download your information** → request **JSON**, Messages only → upload the `.zip`.
  - *WhatsApp:* open the chat with the ex → ⋯ → **Export chat** → **Without media** → AirDrop/email the `.txt` to themselves → upload.
  - *iPhone (iMessage/SMS):* set Messages → Keep Messages = **Forever**, then make an **unencrypted** backup via the Apple Devices app (Windows) → the wizard explains where `sms.db` lands → upload (or upload a 3uTools/iMazing text export).
  - *WeChat:* primary = run the bundled local-decrypt helper (PC, logged in) which produces a `.txt`; fallback = paste/upload plaintext.
- **Format auto-detection** on upload (sniff JSON keys / `_chat.txt` header / SQLite magic / XML root) → routes to the right parser; the friend never picks a format.
- **Instant parse preview** — after upload, show "✓ 4,213 messages from **[ex]**, [date]–[date]" + a few sample lines, so they get immediate confidence before distillation.
- **Always-available plaintext paste** as the universal fallback (esp. WeChat), so no one is ever stuck.

---

## 11. Distillation pipeline (Claude + vendored ex-skill prompts)

`prompts/` adapted from `ex-skill`: `intake.md` (3-question collection), `memories_analyzer.md` + `memories_builder.md` (Track A → `memories.md`), `persona_analyzer.md` + `persona_builder.md` (Track B → 5-layer `persona.md`, incl. the tag→Layer-0 translation table + bilingual signals), `merger.md` (incremental re-distill), `correction_handler.md` ("she'd never say that…"). Driven by the `anthropic` SDK (placeholder key). Output: `persona.md`, `memories.md`, `meta.json` (name, slug, profile, tags{personality[],attachment}, knowledge_sources[], corrections_count, version) — stored encrypted, versioned (keep last 10).

### 11.1 Improvements to the vendored ex-skill assets (owner granted latitude to improve)

`ex-skill` was built for an *interactive Claude Code chat*, not an SMS bot with a separate local model. We improve, not just copy:

1. **SMS-native output** — adapt the persona/builder prompts and the engine's few-shot to produce short, fragmentary, multi-bubble *texty* replies (with a bubble delimiter), instead of long chat paragraphs.
2. **Explicit language-mirroring** — add a rule to persona Layer 2 (expression) + the live system prompt ("reply in the language the user just used"), since the local Qwen model code-switches.
3. **New crisis-safety layer** — `ex-skill` has none; the deterministic bilingual tripwire (§12) is a genuine, important addition.
4. **Hardened parsers** — fold the verified fixes into the parsers (iMessage `attributedBody`→`pytypedstream` + per-row ns/sec date branching, Instagram `ftfy` mojibake + schema-generation handling, WhatsApp `chat-miner` + zh-locale `上午/下午`), beyond `ex-skill`'s originals.
5. **Clean Claude/local split** — distillation is an explicit Claude-API pipeline; the live voice is a local-model prompt assembled deterministically. The two are cleanly separated (ex-skill conflated them into the host agent).
6. **Machine-readable persona** — emit `persona.json` alongside `persona.md` for deterministic, testable prompt assembly (markdown stays human-editable for corrections).
7. **meta.json extensions** — add channel/number binding, subscription-state hooks, and safety/kill-switch flags.
8. **Living voice via periodic re-tuning** (§9.1) — the persona's *expression* adapts to the ongoing conversation every ~100 messages while core personality stays frozen; `ex-skill` had only static distillation + manual corrections.
9. **Polished product surface** — `ex-skill` was a CLI/Claude-Code skill with no UI; we add the Tinder-style guided web wizard (§2, §10.1) so a non-technical friend can self-serve end-to-end.

---

## 12. Safety & privacy

- **Crisis tripwire (deterministic, pre-model, bilingual):** regex/keyword set for self-harm/suicide (zh + en) runs **before** the LLM. On hit → **bypass the persona**, send a fixed message with **988** + a local hotline, write `safety_events`, alert the operator. Never rely on the model's own refusal (jailbreakable).
- **Kill-switch:** per-number flag + a global env switch to silence all replies instantly.
- **Rate caps:** per-peer message ceiling/min to bound cost and runaway loops.
- **Privacy:** all chat data + artifacts Fernet-encrypted at rest; nothing leaves the box except the one-time Claude distillation call (disclosed to the friend in the wizard). Operator-only alerts; no third-party analytics.

---

## 13. Error handling / failure modes

- **Ollama slow/down** → webhook already acked; BackgroundTask retries; last resort = an in-character stall ("phone's dying, brb") rather than an error or broken character.
- **Parser fail / unknown format** → fall back to plaintext; portal surfaces a clear manual-paste path (esp. WeChat).
- **Claude distill fail** → retry w/ backoff; friend can re-run; never blocks the account.
- **Twilio webhook** → always ack empty + reply async; signature failures → 403.
- **Stripe webhook** → verify signature; idempotent handlers keyed by event id.
- **Tunnel down** → health endpoint + auto-restart the cloudflared service; Twilio retries inbound.

---

## 14. Testing (mock-based — no live keys this session)

- **Parsers:** unit tests vs sample exports — `ex-skill`'s `example_xiaomei` + synthetic iMessage `sms.db`, Instagram JSON (incl. mojibake), WhatsApp iOS+Android+zh-locale, WeChat text fallback.
- **Safety:** bilingual crisis phrases must trip; benign must not.
- **Distillation:** mocked `anthropic` client → golden `persona.md`/`memories.md`.
- **Conversation engine:** mocked Ollama (deterministic) → persona consistency, bubble split, history/summary rollover.
- **Messaging:** simulated Twilio `POST` → assert empty TwiML + outbound `Messages.create` called with expected bubbles; signature validation.
- **Billing:** mocked Stripe events → subscription state transitions + activation gating.
- **Manual (on your machine):** trial-number E2E with the friend's verified phone before the paid upgrade.

---

## 15. Config & secrets — ALL placeholders

`.env.example` (real `.env` git-ignored):
```
APP_URL=https://ex.yang9ru.online
JWT_SECRET=__PLACEHOLDER__
FERNET_KEY=__PLACEHOLDER__              # cryptography.fernet.Fernet.generate_key()
ANTHROPIC_API_KEY=__PLACEHOLDER__
ANTHROPIC_MODEL=claude-opus-4-8        # distillation
TWILIO_ACCOUNT_SID=__PLACEHOLDER__
TWILIO_AUTH_TOKEN=__PLACEHOLDER__
TWILIO_FROM_NUMBER=__PLACEHOLDER__      # trial/toll-free number
STRIPE_SECRET_KEY=__PLACEHOLDER__
STRIPE_WEBHOOK_SECRET=__PLACEHOLDER__
STRIPE_PRICE_ID=__PLACEHOLDER__
STRIPE_PUBLISHABLE_KEY=__PLACEHOLDER__  # frontend
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b-instruct-q4_K_M
OLLAMA_EMBED_MODEL=bge-m3
OLLAMA_NUM_PARALLEL=1
STYLE_RETUNE_EVERY=100                  # re-tune voice every N messages/conversation (§9.1)
CLOUDFLARE_TUNNEL_TOKEN=__PLACEHOLDER__
OPERATOR_ALERT_EMAIL=__PLACEHOLDER__
KILL_SWITCH=false
```
Code reads config via a typed settings object; missing secrets fail loud **at the boundary call**, not at import — so the scaffold runs, imports, and tests (mocked) pass without real keys.

---

## 16. Phased roadmap — what I build now vs what you finish

**This session (me) — the infrastructure:** the complete code scaffold for every component above, with placeholder config and mock-based tests, committed and pushed to `Talk_To_Ex`. No live API calls; Ollama/Twilio/Stripe/Claude all behind configurable clients.

**On your machine (you / the continuation agent) — bring-up order:**
- **Phase 0 — Pipe:** install deps, fill `.env`, `ollama pull` the models, start cloudflared tunnel to `ex.yang9ru.online`, point a Twilio **trial** number's webhook at it; confirm an inbound text hits the webhook and a **hardcoded** reply comes back.
- **Phase 1 — Brain (MVP):** real Ollama replies from a hand-written persona; history + bubble-split + safety tripwire. **← you can text the number and get in-character replies.**
- **Phase 2 — Ingestion + distillation:** upload (WhatsApp/plaintext first → iMessage, Instagram, then WeChat) → Claude distill → real persona.
- **Phase 3 — Portal + billing:** wizard live, Stripe **test mode** products + webhook, encryption-at-rest verified.
- **Phase 4 — Reveal:** corrections/versioning, upgrade to **paid toll-free**, operator dashboard/kill-switch, real Stripe price.

---

## 17. Repo layout (`Talk_To_Ex`)

```
Talk_To_Ex/
  backend/
    app/
      main.py            # FastAPI app, static mount, router include
      config.py          # typed settings (env)
      db.py              # SQLModel engine + models
      crypto.py          # Fernet helpers
      auth/              # jwt.py, routes.py, deps.py
      billing/           # stripe_service.py, routes.py, webhook.py
      ingestion/
        upload.py
        normalize.py
        parsers/ imessage.py sms.py instagram.py whatsapp.py wechat.py plaintext.py
      distill/
        prompts/         # vendored from ex-skill (verbatim)
        pipeline.py      # anthropic client
      persona/ store.py schema.py embed.py
      convo/ engine.py history.py summary.py ollama_client.py
      messaging/ twilio_webhook.py sender.py safety.py
    tests/               # mock-based, per §14
    requirements.txt
    .env.example
  frontend/              # Vite + React + TS + Tailwind wizard
    src/{pages,components,api,lib}
    .env.example
  ops/
    cloudflared/         # config.yml.example + Windows-service notes
    ollama/              # Modelfile + setup.md
  docs/superpowers/specs/2026-06-24-talk-to-ex-design.md
  README.md              # quickstart + the bring-up phases
  .gitignore
```

---

## 18. Handoff — continuation prompt (delivered at end of build)

When the scaffold is pushed, you'll get a ready-to-paste prompt for the Claude Code agent on your model-hosting machine: `git clone` the repo, create a venv + `pip install`, `npm install` the frontend, copy `.env.example`→`.env` and fill keys, `ollama pull` both models, set `OLLAMA_NUM_PARALLEL=1`, run migrations, start the app + cloudflared tunnel, point the Twilio trial number's webhook at `ex.yang9ru.online`, then walk Phases 0→4. Includes the verified gotchas inline (attributedBody, mojibake, num_ctx, toll-free consent).

---

## 19. Open questions / risks

- **WeChat tooling currency** — may need a fresh extractor at bring-up; plaintext-paste fallback guarantees the feature still ships.
- **Qwen persona-name leak / code-switching** — needs a smoke test + possible custom Modelfile on your machine.
- **Toll-free verification lead time** — a few days; start it early if a hard reveal date exists.
- **GitHub push auth** — I'll push via `gh`/git if credentials are available; otherwise I'll stage the commit and you run the push.
- **Where the build lands** — built in the current working dir and pushed to `Talk_To_Ex`; the continuation agent pulls onto the model-host machine.
