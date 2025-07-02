"""
Configuration for rate limiting system.
"""

from dataclasses import dataclass
from typing import Optional
import os\nfrom app.core.settings import settings\n\n\ndef parse_boolean_env(value: str) -> bool:\n    \"\"\"\n    Parse environment variable as boolean with support for multiple truthy values.\n    \n    Recognizes: 'true', '1', 'yes', 'on' (case insensitive) as True\n    Everything else as False\n    \"\"\"\n    return value.lower() in ('true', '1', 'yes', 'on')"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting system."""
    
    # Gemini 2.5 Flash limits (80% of free tier)
    flash_rpm_limit: int = 8    # 80% of 10 RPM
    flash_rpd_limit: int = 200  # 80% of 250 RPD
    
    # Gemini 2.5 Pro limits (80% of free tier)
    pro_rpm_limit: int = 4      # 80% of 5 RPM
    pro_rpd_limit: int = 80     # 80% of 100 RPD
    
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
            
        if self.pro_rpm_limit <= 0 or self.pro_rpd_limit <= 0:
            raise ValueError("Pro rate limits must be positive")
            
        if self.circuit_breaker_failure_threshold <= 0:
            raise ValueError("Circuit breaker failure threshold must be positive")
    
    @classmethod
    def from_environment(cls) -> "RateLimitConfig":
        """Create configuration from environment variables."""
        import os
        
        return cls(
            flash_rpm_limit=int(os.getenv("GEMINI_FLASH_RPM_LIMIT", "8")),
            flash_rpd_limit=int(os.getenv("GEMINI_FLASH_RPD_LIMIT", "200")),
            pro_rpm_limit=int(os.getenv("GEMINI_PRO_RPM_LIMIT", "4")),
            pro_rpd_limit=int(os.getenv("GEMINI_PRO_RPD_LIMIT", "80")),
            redis_url=os.getenv("RATE_LIMIT_REDIS_URL", settings.redis_url),
            redis_key_prefix=os.getenv("RATE_LIMIT_REDIS_PREFIX", "mb_sparrow_rl"),
            redis_db=int(os.getenv("RATE_LIMIT_REDIS_DB", "3")),
            circuit_breaker_enabled=parse_boolean_env(os.getenv("CIRCUIT_BREAKER_ENABLED", "true")),
            circuit_breaker_failure_threshold=int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")),
            circuit_breaker_timeout_seconds=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60")),
            safety_margin=float(os.getenv("RATE_LIMIT_SAFETY_MARGIN", "0.2")),
            monitoring_enabled=parse_boolean_env(os.getenv("RATE_LIMIT_MONITORING_ENABLED", "true")),
        )
    
    def get_effective_limits(self, model: str) -> tuple[int, int]:
        """Get effective RPM and RPD limits for a model."""
        if model == "gemini-2.5-flash":
            return self.flash_rpm_limit, self.flash_rpd_limit
        elif model == "gemini-2.5-pro":
            return self.pro_rpm_limit, self.pro_rpd_limit
        else:
            raise ValueError(f"Unknown model: {model}")
    
    def get_redis_keys(self, model: str) -> tuple[str, str]:
        """Get Redis keys for RPM and RPD tracking."""
        model_key = model.replace(".", "_").replace("-", "_")
        rpm_key = f"{self.redis_key_prefix}:{model_key}:rpm"
        rpd_key = f"{self.redis_key_prefix}:{model_key}:rpd"
        return rpm_key, rpd_key