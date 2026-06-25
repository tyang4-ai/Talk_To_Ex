# Talk_To_Ex — Design Spec v2 Addendum

- **Date:** 2026-06-25
- **Status:** Draft for review
- **Extends:** [`2026-06-24-talk-to-ex-design.md`](2026-06-24-talk-to-ex-design.md) (the "v1 spec"). Section numbers here **continue** the v1 spec (§20+) and cross-reference it as **D§n**. Where a row conflicts with v1, this addendum **supersedes** it and says so.
- **Plan:** [`../plans/2026-06-25-talk-to-ex-v2.md`](../plans/2026-06-25-talk-to-ex-v2.md).

This addendum captures the product direction decided after the v1 scaffold was built and brought up locally. It turns the tool from a reactive SMS persona into a small, real-feeling **SaaS**: content-routed hybrid models, a per-persona **fine-tune-on-signup** pipeline with a suspenseful async "reveal," a **freemium → subscription** billing model, and two UX quality-of-life features (portal i18n + guided per-platform upload).

---

## 20. What changed since v1 — and what's already built

The v1 scaffold (D§0–§19) shipped: FastAPI monolith, parsers, Claude distillation, the local conversation engine, Stripe gate, deterministic crisis safety, and the Tinder-style wizard — all with mock tests. During local bring-up (2026-06-24/25) the following landed **on top of v1** and are already in `main`:

- **Hybrid content-routed model selection** (§22) — `app/convo/model_router.py` + config + engine wiring + tests. **Implemented.**
- **Ollama `keep_alive` fix** — the client sent the string `"-1"`, which Ollama 400s (`missing unit in duration`); now sends the integer `-1`. **Fixed.**
- **Reproducible parser fixtures** — `conftest.py` generates the git-ignored iMessage/WeChat `.db` fixtures so `pytest` is green on a fresh clone. **Fixed.**

Everything else in this addendum (§23–§27) is **new design, not yet built** — the plan addendum sequences it.

---

## 21. Hosting topology (revised) — supersedes D§1 "AI hosting" and extends D§3

v1 assumed one Windows box runs everything (app + Ollama + tunnel). The revised topology splits **compute** from **serving**, over the operator's private **Tailscale** mesh:

```
                         Tailscale (private mesh — NOT public)
 ┌─────────────────────────────┐            ┌──────────────────────────────────┐
 │  desktopofyang (RTX 4090)    │            │  serverofyang = "atlas" (Tesla T4) │
 │  • FastAPI app + tunnel      │── HTTP ───▶│  • Ollama (qwen2.5:14b, gemma3:12b)│
 │  • Fine-tune TRAINING jobs   │  :11434    │  • live inference (always-on)      │
 │    (QLoRA on the 4090)       │            │                                    │
 └─────────────────────────────┘            └──────────────────────────────────┘
            ▲                                  100.73.71.126  (Tailscale IP)
   Cloudflare tunnel → ex.yang9ru.online → localhost:8080 (app)
```

- **Inference host = atlas (Tesla T4, 15 GB).** Always-on Linux server, Ollama already installed; `OLLAMA_BASE_URL=http://100.73.71.126:11434`. For async SMS, the T4's ~7–10 tok/s is ample (replies are async with intentional 1–3 s bubble delays per D§9).
- **Training host = the 4090 (24 GB).** QLoRA fine-tuning a 14B needs more VRAM than inference; the T4 is too small to train, the 4090 is well-suited (§23). The app + tunnel also run here.
- **Privacy invariant preserved (D§12):** Ollama is reachable only on the private tailnet, never via the Cloudflare tunnel and never on the public internet. "Chat data never leaves the box" becomes "never leaves the operator's own private mesh" — a deliberate, disclosed relaxation, since atlas is the operator's own machine.
- **Benchmark basis (2026-06-24):** same model, the 4090 is ~8–12× faster than the T4 (qwen14b 7→82 tok/s; gemma12b 10→79). The 4090 can also run bigger models (gemma3:27b ~33 tok/s); **qwen2.5:32b q4 does not fit at 8K context** (fills 24 GB, sysmem-thrashes to ~0.3–11 tok/s) — use it only headless or at reduced context. For SMS the 14B/12B class is the sweet spot; bigger models add only marginal nuance.

---

## 22. Hybrid content-routed model selection (IMPLEMENTED) — extends D§9

The friend's uploaded log decides which local model voices the persona. **Chinese-dominant → Qwen** (strongest open bilingual zh); **English-dominant → Gemma**.

- **Module:** `app/convo/model_router.py`. `cjk_ratio(text)` = CJK / (CJK + Latin) over all message text; `detect_dominant_language()` compares it to `MODEL_ROUTE_CJK_THRESHOLD` (default 0.5); `pick_model()` returns `(lang, model)`.
- **Wiring:** at distill time (`persona/routes.distill_persona`) the choice is computed and pinned on the persona (`meta_json["llm_model"]`, `["llm_language"]`); the live engine (`engine.reply`) reads it and builds `OllamaClient(model=...)` per persona. Falls back to `settings.ollama_model` when unset (e.g. hand-written Phase-1 personas).
- **Config:** `OLLAMA_MODEL_ZH=qwen2.5:14b-instruct-q4_K_M`, `OLLAMA_MODEL_EN=gemma3:12b`, `MODEL_ROUTE_CJK_THRESHOLD=0.5`.
- **Smoke-tested on the T4:** no "answers as Qwen" name leak on either model with a proper system prompt; language mirroring works both ways. So the custom ChatML Modelfile D§9 worried about is **not required for now** (kept as a fallback if a leak appears in longer chats).
- **Manual override (NEW, §26):** auto-detect is the default but the wizard exposes it as an editable choice (Qwen / Gemma / Auto). The chosen value overrides the detected `llm_model`.
- **VRAM note:** the T4 (15 GB) holds **one** ~9 GB model resident at a time. A single persona keeps a fixed model, so this is a non-issue in practice; but two simultaneously-active personas of different languages incur a cold model reload (~3–7 s) when traffic alternates. Don't pin both models with `keep_alive:-1` on the T4.

---

## 23. Per-persona fine-tuning — "the ex learns to text like the ex" (NEW)

A local QLoRA fine-tune per persona, on top of the structured prompt persona. This is the headline quality upgrade and the core of the "reveal" (§24).

### 23.1 Why and what
- **Voice authenticity:** prompt-distillation captures personality well; a fine-tune captures the *exact* texting cadence, vocabulary, punctuation, and in-jokes from the real logs in the weights themselves.
- **Privacy:** training is 100% local (on the 4090) — nothing leaves the box. It *reduces* the Claude dependency rather than adding cloud exposure.
- **Claude cannot be fine-tuned** (no Anthropic API for it); OpenAI fine-tuning exists but is a cloud train (data leaves the box, paid) — rejected for the privacy premise. We fine-tune the **local Qwen/Gemma**.

### 23.2 Recommended shape — **hybrid: fine-tune the voice, keep the structure as prompt**
Map the fine-tune onto the persona's existing **Layer 2 (expression/voice)** concept (D§9.1). Keep in the prompt/context (NOT the weights): the structured 5-layer persona, memories, the rolling summary, and — non-negotiably — the **deterministic crisis-safety layer** (D§12). The LoRA adapter only sharpens *how* the persona texts.
- This keeps personality, boundaries, and safety controllable and editable (corrections stay a prompt edit, D§11), while the adapter delivers the voice.
- A **fully-local variant** (skip Claude entirely, derive a minimal persona locally) is possible for maximum privacy / zero API cost, but loses the structured-persona quality and easy corrections — offered as an option, not the default.

### 23.3 Pipeline (runs on the 4090)
1. **Data prep:** convert the normalized transcript into chat-format SFT examples where the **ex (direction `in`) is the assistant** and the friend (`out`) is the user; preserve the zh/en mix; window into short multi-turn samples matching the SMS style.
2. **Train:** QLoRA with **Unsloth** (preferred — fast, low-VRAM, fits a 14B on the 24 GB 4090) or **LLaMA-Factory**. Produces a small LoRA adapter (safetensors).
3. **Convert:** adapter → GGUF (llama.cpp `convert_lora_to_gguf.py`).
4. **Serve:** a per-persona derived Ollama model via a Modelfile: `FROM qwen2.5:14b-instruct-q4_K_M` + `ADAPTER ./persona-<id>.gguf` + the persona system stub → `ollama create persona-<id>`. The engine targets `persona-<id>` for that persona (stored alongside `llm_model`).
5. **Time budget:** **up to ~2 days is acceptable** (operator's call) — jobs run overnight at low priority on the 4090. The wait is a *feature* (§24).

### 23.4 Constraints & risks
- **Adapter↔base compatibility:** verify the GGUF adapter loads cleanly on the chosen base/quant in Ollama on day one — this path has historically been finicky.
- **Overfitting on small logs:** short chat histories overfit; cap epochs, hold out a few turns, sanity-check the persona still language-mirrors and doesn't parrot verbatim.
- **Per-persona model sprawl:** each persona = one derived Ollama model; on the 15 GB T4 only one is resident at a time (cold reload on switch). Fine at single-friend scale; revisit for many concurrent personas.
- **GPU contention:** a 2-day train ties up the 4090; schedule low-priority/overnight, or gate concurrent jobs to one at a time via the job queue (§24, plan E12).

---

## 24. The "reveal" — async fine-tune + proactive opener (NEW) — extends D§6, D§8, D§12

The product moment: the friend finishes setup, sees a playful "your ex is getting ready" screen, and **later receives an unprompted first text** from the persona — an in-character apology — when training completes.

### 24.1 Flow
1. Upload + intake complete → enqueue a fine-tune **job** (§23, plan E12/E13) → persona status `building`.
2. Wizard shows a **fun loading state** ("Your ex is getting ready… expect a message soon 💌"; themed animation — a perpetual "typing…", "reconnecting…"). Frontend-only; zero risk.
3. Job completes (minutes–2 days) → persona goes `active` → the app **sends the first SMS proactively** (the opener).
4. From message 2 onward, the normal reactive engine (D§6) takes over.

### 24.2 The opener — curated, not freely generated
The first message is the entire first impression **and** the one message with no user turn to react to. Therefore:
- **Templated/seeded** (3–4 in-character apology variants), not free generation — controls the vibe and is **safe by construction**.
- Switch to full local-model generation from message 2.

### 24.3 Outbound-initiation compliance (the non-obvious part) — extends D§8
v1 was **purely reactive** (toll-free consent rested on "the friend texts first"). Sending first changes the regulatory category. It's defensible because the friend signed up and gave their own number (that *is* the opt-in), but to stay clean:
- **Record consent:** persist a timestamped opt-in (signup time + number) per persona.
- **Honor STOP/HELP:** Twilio auto-handles the keywords; the app must also respect opt-out via the per-number kill-switch (D§12).
- **Clear sender framing:** the opener must make plain it's from the service the friend signed up for (it can still be styled as the ex). Keep Privacy/Terms URLs live (D§8).

### 24.4 Outbound safety screening — extends D§12
v1's crisis tripwire runs only on **inbound** `/sms`. The proactive opener (and ideally every generated reply) is outbound model-adjacent content and must also pass a safety screen before sending — especially the unprompted opener. Inbound tripwire still applies to everything the friend says once the conversation starts.

---

## 25. Freemium → subscription billing (metered) — extends D§5

Mimic a real SaaS: a free allowance, then a subscription to continue.

- **Meter by MESSAGE COUNT, not tokens.** "200 free messages" is legible to a consumer; tokens are opaque. (Tokens only matter for *our* cost — see below.) Default `FREE_MESSAGE_LIMIT=200` (the friend's inbound messages per persona).
- **Gate location:** in `messaging` `_respond`, before generating a reply: if `inbound_count > FREE_MESSAGE_LIMIT` and `subscription_status != active` → send a **templated paywall message** ("You've used your free messages — subscribe to keep texting 🔗 <checkout link>") **instead of** the persona reply. The existing Stripe Checkout subscription + signed webhook (D§5) flips `subscription_status` and unlocks replies.
- **Economics (why this works):** live inference is **local and ~free** (electricity only). Our only real costs are the one-time Claude distillation (~$0.45–$2/persona, or $0 in the fully-local variant) and the toll-free number (~$2.15/mo). So the 200-message free tier is nearly costless, and a $5–10/mo subscription is almost pure margin — it mainly covers the number. The free tier is a genuine try-before-you-buy, not a loss leader.
- **Optional later:** usage tiers, a per-persona one-time "unlock," or annual pricing. Out of scope for v2.

---

## 26. QoL — portal i18n + user-selectable model (NEW) — extends D§2, §22

Two distinct knobs, often conflated:

- **(a) Portal UI language (zh/en).** Standard interface i18n via `react-i18next` + `zh`/`en` locale files + a switcher in the wizard. Independent of the persona's model — a friend may prefer the English UI but have a Chinese-texting ex.
- **(b) Persona model selection.** Surface the auto-detected model (§22) as a confirm/override step: *"We detected mostly Chinese → your ex will run on Qwen. [Change ▾]"* with options Qwen / Gemma / Auto. Word it as the persona's **primary voice**, not a hard "Chinese vs English" — many exes are bilingual, and **Qwen handles mixed best**, so Qwen is the safe default for mixed logs; Gemma is the "basically English-only" choice. The chosen value writes `llm_model`/`llm_language` on the persona (D§22 wiring).

---

## 27. Guided per-platform upload UX (concretized) — extends D§10.1

Self-upload is the **only** way to obtain a person's private chat history — no platform exposes it via API to third parties, and the upload model is also the correct consent posture (the friend exports **their own** data). So invest in making it effortless:

- **Dropdown / accordion picker** in the import wizard: *"I'm uploading from: iMessage / WhatsApp / Instagram / WeChat / Android SMS / paste text"* → per-platform step-by-step guide. Backed by the existing format list (D§10) and auto-detection (which still runs on the uploaded file).
- **OS variants:** WhatsApp and iMessage export differently on iOS vs Android — show the right variant (sub-toggle or OS detection).
- **Screenshots — make your own, do NOT lift from forums.** Forum/blog screenshots carry copyright risk **and** go stale when the apps redesign their export flow. Take your own annotated screenshots on each app (clean, owned, current), or link the official help-doc steps + add a short annotated version.
- **Editable content store:** keep guides as markdown/JSON + image assets (not hardcoded), so they can be updated without a redeploy when an app moves the export button.
- **Keep the universal fallback:** always-available plaintext paste (D§10.1), so no one is ever stuck (esp. WeChat).

---

## 28. Data model & config deltas

**New/changed tables & columns (SQLModel):**
- `jobs`(id, persona_id, kind[`finetune`], status[`queued`|`training`|`ready`|`failed`], adapter_path, error, created_at, updated_at) — the async job queue (§24, §23).
- `personas`: add `llm_model`/`llm_language` (already stored inside `meta_json` today — may promote to columns), `adapter_model` (the `persona-<id>` Ollama name once trained), `status` gains `building`.
- `users` / `personas`: a consent record — `opt_in_at`, `opt_in_number` (§24.3). Metering uses the existing `conversations.message_count` (D§7); add a per-persona/per-user inbound counter if cross-conversation metering is wanted.
- `safety_events`: add `direction` so outbound screens (§24.4) are logged distinctly from inbound trips.

**New config keys (extend D§15):**
```
OLLAMA_MODEL_ZH=qwen2.5:14b-instruct-q4_K_M   # §22 (implemented)
OLLAMA_MODEL_EN=gemma3:12b                     # §22 (implemented)
MODEL_ROUTE_CJK_THRESHOLD=0.5                  # §22 (implemented)
FREE_MESSAGE_LIMIT=200                         # §25
FINETUNE_ENABLED=true                          # §23 — off → fall back to prompt-only persona
FINETUNE_TRAINER=unsloth                        # §23 — unsloth | llama-factory
TRAIN_OLLAMA_HOST=http://localhost:11434        # §23 — where derived models are created (the 4090)
```
`OLLAMA_BASE_URL` now points at atlas (`http://100.73.71.126:11434`, §21).

---

## 29. Open questions / risks (extends D§19)

- **Outbound compliance** (§24.3) — confirm toll-free verification copy covers a service-initiated first message; keep STOP/HELP + consent records audited.
- **Fine-tune infra** (§23) — Unsloth vs LLaMA-Factory choice; GGUF-adapter↔Ollama compatibility must be proven on the 4090 day one; overfitting guardrails on short logs.
- **Per-persona model sprawl / T4 VRAM** (§22, §23.4) — one resident model at a time; fine for one friend, revisit at scale.
- **Freemium abuse** — message-count gate is per persona; decide whether a new persona resets the free tier (and whether that's exploitable).
- **Screenshot maintenance** (§27) — own screenshots need periodic refresh as apps redesign exports.
- **Whole-app-on-atlas option** — if the desktop shouldn't be always-on, the app+tunnel could also move to atlas (Linux); training would still need the 4090. Deferred decision.
