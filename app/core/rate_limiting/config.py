"""
Configuration for rate limiting system.
"""

from dataclasses import dataclass
import os
import re

from app.core.settings import settings

def parse_boolean_env(value: str) -> bool:
    """
    Parse environment variable as boolean with support for multiple truthy values.
    
    Recognizes: 'true', '1', 'yes', 'on' (case insensitive) as True
    Everything else as False
    """
    return str(value).lower() in ('true', '1', 'yes', 'on')


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting system."""

    # Gemini 3.0 Pro limits (preview tier)
    gemini_3_pro_rpm_limit: int = 5    # Preview: 5 RPM
    gemini_3_pro_rpd_limit: int = 200  # Preview: 200 RPD

    # Gemini 2.5 Flash limits (free tier)
    flash_rpm_limit: int = 10   # Free tier: 10 RPM
    flash_rpd_limit: int = 250  # Free tier: 250 RPD

    # Gemini 2.5 Flash-Lite limits (free tier)
    flash_lite_rpm_limit: int = 15   # Free tier: 15 RPM
    flash_lite_rpd_limit: int = 1000  # Free tier: 1,000 RPD

    # Gemini 2.5 Pro limits (free tier)
    pro_rpm_limit: int = 2       # Free tier: 2 RPM
    pro_rpd_limit: int = 50      # Free tier: 50 RPD
    
    # Redis configuration
    redis_url: str = settings.redis_url
    redis_key_prefix: str = "mb_sparrow_rl"
    redis_db: int = 3  # Dedicated database for rate limiting
    
    # Circuit breaker configuration
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 60
    circuit_breaker_success_threshold: int = 3  # Successes needed to close in HALF_OPEN
    
    # Safety configuration
    safety_margin: float = 0.2  # 20% safety margin
    enable_burst_allowance: bool = True  # Allow short bursts
    burst_capacity_multiplier: float = 1.5  # 150% of normal capacity for bursts

    # Free tier backpressure configuration
    enable_backpressure: bool = True  # Wait for RPM window instead of failing fast
    backpressure_max_wait_seconds: int = 8  # Cap wait per retry window
    backpressure_retry_attempts: int = 3  # Attempts before surfacing 429
    backpressure_jitter_seconds: float = 0.35  # Random jitter to avoid thundering herd
    
    # Monitoring configuration
    monitoring_enabled: bool = True
    metrics_retention_hours: int = 24
    alert_threshold_percentage: float = 0.9  # Alert when 90% of limit used
    
    # Performance configuration
    redis_connection_timeout: int = 5
    redis_operation_timeout: int = 1
    max_retry_attempts: int = 3
    retry_backoff_factor: float = 0.5
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.safety_margin < 0 or self.safety_margin > 0.5:
            raise ValueError("Safety margin must be between 0 and 0.5")
        
        if self.flash_rpm_limit <= 0 or self.flash_rpd_limit <= 0:
            raise ValueError("Flash rate limits must be positive")
        if self.flash_lite_rpm_limit <= 0 or self.flash_lite_rpd_limit <= 0:
            raise ValueError("Flash Lite rate limits must be positive")
            
        if self.pro_rpm_limit <= 0 or self.pro_rpd_limit <= 0:
            raise ValueError("Pro rate limits must be positive")
            
        if self.circuit_breaker_failure_threshold <= 0:
            raise ValueError("Circuit breaker failure threshold must be positive")
    
    @classmethod
    def from_environment(cls) -> "RateLimitConfig":
        """Create configuration from environment variables."""
        import os

        return cls(
            gemini_3_pro_rpm_limit=int(os.getenv("GEMINI_3_PRO_RPM_LIMIT", "20")),
            gemini_3_pro_rpd_limit=int(os.getenv("GEMINI_3_PRO_RPD_LIMIT", "1000")),
            flash_rpm_limit=int(os.getenv("GEMINI_FLASH_RPM_LIMIT", "10")),
            flash_rpd_limit=int(os.getenv("GEMINI_FLASH_RPD_LIMIT", "250")),
            flash_lite_rpm_limit=int(os.getenv("GEMINI_FLASH_LITE_RPM_LIMIT", "15")),
            flash_lite_rpd_limit=int(os.getenv("GEMINI_FLASH_LITE_RPD_LIMIT", "1000")),
            pro_rpm_limit=int(os.getenv("GEMINI_PRO_RPM_LIMIT", "10")),
            pro_rpd_limit=int(os.getenv("GEMINI_PRO_RPD_LIMIT", "400")),
            redis_url=os.getenv("RATE_LIMIT_REDIS_URL", settings.redis_url),
            redis_key_prefix=os.getenv("RATE_LIMIT_REDIS_PREFIX", "mb_sparrow_rl"),
            redis_db=int(os.getenv("RATE_LIMIT_REDIS_DB", "3")),
            circuit_breaker_enabled=parse_boolean_env(os.getenv("CIRCUIT_BREAKER_ENABLED", "true")),
            circuit_breaker_failure_threshold=int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")),
            circuit_breaker_timeout_seconds=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60")),
            safety_margin=float(os.getenv("RATE_LIMIT_SAFETY_MARGIN", "0.2")),
            monitoring_enabled=parse_boolean_env(os.getenv("RATE_LIMIT_MONITORING_ENABLED", "true")),
            enable_backpressure=parse_boolean_env(os.getenv("RATE_LIMIT_ENABLE_BACKPRESSURE", "true")),
            backpressure_max_wait_seconds=int(os.getenv("RATE_LIMIT_BACKPRESSURE_MAX_WAIT", "8")),
            backpressure_retry_attempts=int(os.getenv("RATE_LIMIT_BACKPRESSURE_RETRIES", "3")),
            backpressure_jitter_seconds=float(os.getenv("RATE_LIMIT_BACKPRESSURE_JITTER", "0.35")),
        )
    
    def get_effective_limits(self, model: str) -> tuple[int, int]:
        """Get effective RPM and RPD limits for a model."""
        normalized = self.normalize_model_name(model)

        if normalized == "gemini-3-pro":
            return self.gemini_3_pro_rpm_limit, self.gemini_3_pro_rpd_limit
        if normalized == "gemini-2.5-flash":
            return self.flash_rpm_limit, self.flash_rpd_limit
        if normalized == "gemini-2.5-flash-lite":
            return self.flash_lite_rpm_limit, self.flash_lite_rpd_limit
        elif normalized == "gemini-2.5-pro":
            return self.pro_rpm_limit, self.pro_rpd_limit
        else:
            raise ValueError(f"Unknown model: {model}")

    def get_redis_keys(self, model: str) -> tuple[str, str]:
        """Get Redis keys for RPM and RPD tracking."""
        normalized = self.normalize_model_name(model)
        model_key = normalized.replace(".", "_").replace("-", "_")
        rpm_key = f"{self.redis_key_prefix}:{model_key}:rpm"
        rpd_key = f"{self.redis_key_prefix}:{model_key}:rpd"
        return rpm_key, rpd_key

    @staticmethod
    def normalize_model_name(model: str) -> str:
        """Normalize Gemini model variants to their base family names."""
        candidate = (model or "").strip().lower()
        if not candidate:
            raise ValueError("Model name is required for normalization")

        candidate = candidate.replace(" ", "")
        if candidate.startswith("models/"):
            candidate = candidate[len("models/"):]

        # Order matters: check more specific patterns first (e.g., flash-lite before flash)
        base_candidates = (
            "gemini-3-pro",         # Gemini 3.0 Pro (newest)
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        )

        for base in base_candidates:
            if candidate.startswith(base):
                return base

        # Strip common variant suffixes (preview tags, numbered builds, fine-tunes, etc.)
        stripped = re.sub(
            r"-(preview(?:-[0-9a-z]+)*|beta|alpha|exp(?:erimental)?|test(?:ing)?|staging|v\d+|r\d+|ft[0-9a-z-]*|\d{3}|ga|rc).*",
            "",
            candidate,
        )

        for base in base_candidates:
            if stripped.startswith(base):
                return base

        raise ValueError(f"Unsupported Gemini model: {model}")
