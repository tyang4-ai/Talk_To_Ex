"""Typed settings. Secrets default to "" so the app imports without real keys;
call require() at the boundary where a secret is actually needed."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_url: str = "https://ex.yang9ru.online"
    jwt_secret: str = ""
    fernet_key: str = ""

    # Claude (distillation + style re-tuning)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # Twilio (SMS)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # Stripe (billing)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id: str = ""
    stripe_publishable_key: str = ""

    # Ollama (local model)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct-q4_K_M"  # fallback when a persona has no routed model
    ollama_embed_model: str = "bge-m3"
    ollama_num_parallel: int = 1
    style_retune_every: int = 100

    # Hybrid model routing: the dominant language of the friend's uploaded log
    # picks the local model — Chinese -> Qwen (best bilingual zh), English ->
    # Gemma. Chosen once at distill time, stored on the persona, used per reply.
    ollama_model_zh: str = "qwen2.5:14b-instruct-q4_K_M"
    ollama_model_en: str = "gemma3:12b"
    model_route_cjk_threshold: float = 0.5  # CJK char fraction >= this -> zh (Qwen)

    # Per-persona fine-tuning (spec §23). Off → personas use the prompt-only path.
    finetune_enabled: bool = True
    finetune_trainer: str = "unsloth"  # unsloth | llama-factory (host-only)
    train_ollama_host: str = "http://localhost:11434"  # where derived models are created (the 4090)

    # Freemium metering (spec §25): N free inbound messages per persona, then the
    # owner must have an active subscription to keep getting replies.
    free_message_limit: int = 200

    # Master billing switch. When False the paywall is disabled entirely (free for
    # everyone) — independent of demo_mode, so live Claude distillation and Twilio
    # SMS still run normally. Flip True (and wire Stripe) to start charging.
    require_subscription: bool = True

    # AI spend guardrails for the PUBLIC service — the owner's hard backstop
    # against a runaway Anthropic bill. A global daily ceiling across every real
    # Claude call (distill + corrections + style re-tune), an instant off-switch,
    # and per-user caps. (Set a spend limit in the Anthropic console too.)
    max_claude_calls_per_day: int = 50
    claude_kill_switch: bool = False
    max_personas_per_user: int = 10
    max_corrections_per_persona: int = 20
    max_correction_chars: int = 500

    # Demo mode (spec: localhost dry-run) — bypass the paid externals (Claude
    # distillation, Stripe gate, Twilio number) with local fallbacks so the whole
    # wizard is clickable end-to-end with NO external accounts. OFF in production.
    demo_mode: bool = False

    # Ops / safety
    cloudflare_tunnel_token: str = ""
    operator_alert_email: str = ""
    kill_switch: bool = False

    database_url: str = "sqlite:///./talk_to_ex.db"


settings = Settings()


def require(name: str) -> str:
    """Return a secret or raise — used at the boundary call, never at import."""
    val = getattr(settings, name, "")
    if not val:
        raise RuntimeError(f"Missing required secret: {name} — set it in backend/.env")
    return val
