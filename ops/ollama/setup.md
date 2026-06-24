# Ollama setup (Windows host)

Talk_To_Ex answers live texts with a **local** model so chat data never leaves the
box. Only the one-time persona distillation (and the ~1-per-100-message style
re-tune) calls the Claude API; everything else is on-device.

> Ollama listens on `127.0.0.1:11434`. **This port is NEVER tunnelled or exposed.**
> Only the FastAPI app (`localhost:8080`) goes through Cloudflare.

## 1. Install Ollama

Download the Windows installer from <https://ollama.com/download> and run it, or:

```powershell
winget install Ollama.Ollama
```

Confirm it's up:

```powershell
ollama --version
ollama list
```

## 2. Pull the models

```powershell
# Chat model — qwen2.5 14B, q4_K_M quant (~9.0 GB on disk; fits 16 GB VRAM with headroom)
ollama pull qwen2.5:14b-instruct-q4_K_M

# Embedding model — used for optional bge-m3 top-k RAG when memories outgrow the
# context budget. Safe to pull now even if RAG is off.
ollama pull bge-m3
```

These names match `OLLAMA_MODEL` / `OLLAMA_EMBED_MODEL` in `backend/.env`. If you
change a name here, change it there too.

## 3. (Recommended) Build the custom persona model

The base Qwen model sometimes ignores the runtime system prompt and answers as
"Qwen" (Ollama #6873). The bundled `Modelfile` bakes in a ChatML system stub +
the required params to make the persona/name stick:

```powershell
cd ops/ollama
ollama create talk-to-ex -f Modelfile
ollama run talk-to-ex   # smoke-test: it should answer in character, not as "Qwen"
```

Then set `OLLAMA_MODEL=talk-to-ex` in `backend/.env`. (Leaving the default
`qwen2.5:14b-instruct-q4_K_M` also works — the engine sets the same params per
request — but the custom model is the more reliable fix for the name leak.)

## 4. Set OLLAMA_NUM_PARALLEL=1 (important)

The KV cache size is `num_ctx * OLLAMA_NUM_PARALLEL`. The VRAM-tiering logic
ignores parallelism when picking `num_ctx`, so leaving parallelism at its default
(>1) can silently blow the cache or shrink usable context. With one user we want
all the VRAM going to a single 8K-context request:

Set it as a **system** environment variable so the Ollama background service
picks it up (a per-shell variable won't reach the service):

```powershell
# Persist for the machine, then restart the Ollama service so it takes effect.
setx OLLAMA_NUM_PARALLEL 1 /M
Restart-Service Ollama   # or quit + relaunch Ollama from the tray
```

Verify after restart:

```powershell
[Environment]::GetEnvironmentVariable("OLLAMA_NUM_PARALLEL","Machine")
```

`backend/.env` also carries `OLLAMA_NUM_PARALLEL=1`; that value is for the app's
own bookkeeping. The one that actually changes Ollama's behavior is this
machine-level variable read by the Ollama service.

## 5. keep_alive — keep the model resident

Cold-loading a 9 GB model on every text adds many seconds of latency and risks the
Twilio webhook timeout window. The conversation engine sends `keep_alive: "-1"` on
every `/api/chat` call, which tells Ollama to **keep the model loaded
indefinitely** instead of evicting it after the default 5 minutes.

- You don't need to configure this — the app sends it per request. Just be aware
  the model will stay resident in VRAM after the first text. That's intentional.
- To force-unload manually (e.g. to free VRAM): `ollama stop qwen2.5:14b-instruct-q4_K_M`
  (or `ollama stop talk-to-ex`).
- If you ever want a global default instead of per-request, set
  `OLLAMA_KEEP_ALIVE=-1` as a machine env var the same way as step 4.

## 6. Quick sanity check (matches what the app sends)

```powershell
curl http://localhost:11434/api/chat -Method POST -Body (@{
  model = "qwen2.5:14b-instruct-q4_K_M"
  stream = $false
  keep_alive = "-1"
  options = @{ num_ctx = 8192; temperature = 0.8 }
  messages = @(@{ role = "user"; content = "hey" })
} | ConvertTo-Json -Depth 5) -ContentType "application/json"
```

A JSON reply with a `message.content` field means the local pipe is good. Continue
to the backend quickstart in the root `README.md`.
