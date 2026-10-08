"""Central configuration. All secrets come from environment variables (.env), never from code."""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr: printing/logging the settings object shows '**********' instead of the value.
    DATABASE_URL: SecretStr = SecretStr("postgresql+psycopg://ecommerce:change-me@localhost:5432/ecommerce_ai")
    JWT_SECRET: SecretStr = SecretStr("dev-only-change-me")
    JWT_ALGORITHM: str = "HS256"
    BCRYPT_ROUNDS: int = 12  # tests lower this for speed; keep >= 12 in real deployments
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    FRONTEND_URL: str = "http://localhost:5173"

    # --- AI agent ---
    # "mock"   -> built-in rule-based model (no API key, deterministic, great for learning/tests)
    # "openai" -> any OpenAI-compatible chat-completions endpoint (OpenAI, Ollama, LM Studio, vLLM...)
    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    AGENT_MAX_STEPS: int = 4

    UPLOAD_DIR: str = "uploads"
    SHIPPING_FLAT_FEE: float = 250.0
    FREE_SHIPPING_THRESHOLD: float = 5000.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
