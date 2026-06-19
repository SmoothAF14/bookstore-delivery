"""
config.py — Application settings (pydantic-settings).

Loads configuration from the environment (and a local .env). All delivery
classification / dispatch thresholds are configurable so the rules can be tuned
without code changes.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ───────────────────────────────────────────────────
    app_env: str = "development"
    app_debug: bool = True
    port: int = 8004

    # ── CORS (comma-separated origins) ────────────────────────
    cors_origins: str = "*"

    # ── Upstream services ─────────────────────────────────────
    django_api_url: str = "http://localhost:8000"
    tracking_service_url: str = "http://localhost:8003"

    # ── Celery / Redis ────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ── Auth ──────────────────────────────────────────────────
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_user_id_claim: str = "user_id"
    require_auth: bool = True

    # ── LLM (OpenRouter, OpenAI-compatible) ───────────────────
    # The delivery bot is the 3rd AI feature: an LLM reviews the rule-based
    # classification and may adjust the tier/priority with a short rationale.
    # Uses the SAME LLM_API_KEY as the assistant + tracking bots. When unset,
    # the bot falls back to pure rules so it always works.
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "deepseek/deepseek-v3.2"
    llm_max_tokens: int = 512
    llm_enabled: bool = True

    # ── Classification thresholds ─────────────────────────────
    # An order is EXPRESS when its total value is at or above this (currency
    # units, matching the backend's total_amount).
    express_value_threshold: float = 2000.0
    # An order is BULK when its total item quantity is at or above this.
    bulk_quantity_threshold: int = 10

    # ── Dispatch SLAs (hours from order placement) ────────────
    dispatch_hours_express: int = 2
    dispatch_hours_standard: int = 24
    dispatch_hours_bulk: int = 48
    # When stock is short, hold dispatch this long (awaiting restock).
    dispatch_hours_backorder: int = 120

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def broker_url(self) -> str:
        """Celery broker — explicit override, else the shared Redis."""
        return self.celery_broker_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
