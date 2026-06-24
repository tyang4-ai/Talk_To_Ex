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
    ollama_model: str = "qwen2.5:14b-instruct-q4_K_M"
    ollama_embed_model: str = "bge-m3"
    ollama_num_parallel: int = 1
    style_retune_every: int = 100

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
