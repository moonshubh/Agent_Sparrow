from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

# Load environment variables from project root .env if present
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)

class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    cache_ttl_sec: int = Field(default=3600, alias="CACHE_TTL_SEC")
    router_conf_threshold: float = Field(default=0.6, alias="ROUTER_CONF_THRESHOLD")
    use_enhanced_log_analysis: bool = Field(default=True, alias="USE_ENHANCED_LOG_ANALYSIS")
    enhanced_log_model: str = Field(default="gemini-2.5-pro", alias="ENHANCED_LOG_MODEL")

    class Config:
        case_sensitive = False
        env_file = ENV_PATH

@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()

# Instantiate settings at import time for convenience
settings: Settings = get_settings()
