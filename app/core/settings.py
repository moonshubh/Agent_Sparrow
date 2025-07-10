from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

# Load environment variables from project root .env if present
# Calculate the path safely with depth validation
current_file_path = Path(__file__).resolve()
project_root_depth = 2  # Two levels up from app/core/settings.py to project root

# Validate directory depth to prevent IndexError
if len(current_file_path.parents) <= project_root_depth:
    # Fallback to current directory if path calculation fails
    project_root = Path.cwd()
else:
    project_root = current_file_path.parents[project_root_depth]

ENV_PATH = project_root / ".env"
load_dotenv(ENV_PATH)

class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    cache_ttl_sec: int = Field(default=3600, alias="CACHE_TTL_SEC")
    router_conf_threshold: float = Field(default=0.6, alias="ROUTER_CONF_THRESHOLD")
    use_enhanced_log_analysis: bool = Field(default=True, alias="USE_ENHANCED_LOG_ANALYSIS")
    enhanced_log_model: str = Field(default="gemini-2.5-pro", alias="ENHANCED_LOG_MODEL")
    
    # FeedMe Configuration
    feedme_enabled: bool = Field(default=True, alias="FEEDME_ENABLED")
    feedme_html_enabled: bool = Field(default=True, alias="FEEDME_HTML_ENABLED")
    feedme_max_file_size_mb: int = Field(default=10, alias="FEEDME_MAX_FILE_SIZE_MB")
    feedme_max_examples_per_conversation: int = Field(default=20, alias="FEEDME_MAX_EXAMPLES_PER_CONVERSATION")
    feedme_embedding_batch_size: int = Field(default=10, alias="FEEDME_EMBEDDING_BATCH_SIZE")
    feedme_max_retrieval_results: int = Field(default=3, alias="FEEDME_MAX_RETRIEVAL_RESULTS")
    
    # FeedMe PDF Support Configuration
    feedme_pdf_enabled: bool = Field(default=True, alias="FEEDME_PDF_ENABLED")
    feedme_max_pdf_size_mb: int = Field(default=20, alias="FEEDME_MAX_PDF_SIZE_MB")
    feedme_pdf_processing_timeout: int = Field(default=30, alias="FEEDME_PDF_PROCESSING_TIMEOUT")
    feedme_pdf_concurrent_limit: int = Field(default=5, alias="FEEDME_PDF_CONCURRENT_LIMIT")
    
    # Enhanced PDF Processing Configuration
    feedme_max_tokens_per_minute: int = Field(default=12000, alias="FEEDME_MAX_TOKENS_PER_MINUTE")
    feedme_max_tokens_per_chunk: int = Field(default=8000, alias="FEEDME_MAX_TOKENS_PER_CHUNK")
    feedme_chunk_overlap_tokens: int = Field(default=500, alias="FEEDME_CHUNK_OVERLAP_TOKENS")
    
    # OCR Processing Configuration
    feedme_ocr_enabled: bool = Field(default=True, alias="FEEDME_OCR_ENABLED")
    feedme_ocr_confidence_threshold: float = Field(default=0.7, alias="FEEDME_OCR_CONFIDENCE_THRESHOLD")
    
    # Quality Control Configuration
    feedme_similarity_threshold: float = Field(default=0.7, alias="FEEDME_SIMILARITY_THRESHOLD")
    feedme_confidence_threshold: float = Field(default=0.7, alias="FEEDME_CONFIDENCE_THRESHOLD")
    
    # Supabase Configuration
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: Optional[str] = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_key: Optional[str] = Field(default=None, alias="SUPABASE_SERVICE_KEY")
    feedme_async_processing: bool = Field(default=True, alias="FEEDME_ASYNC_PROCESSING")
    feedme_celery_broker: str = Field(default="redis://localhost:6379/1", alias="FEEDME_CELERY_BROKER")
    feedme_result_backend: str = Field(default="redis://localhost:6379/2", alias="FEEDME_RESULT_BACKEND")
    feedme_security_enabled: bool = Field(default=True, alias="FEEDME_SECURITY_ENABLED")
    feedme_rate_limit_per_minute: int = Field(default=10, alias="FEEDME_RATE_LIMIT_PER_MINUTE")
    feedme_version_control: bool = Field(default=True, alias="FEEDME_VERSION_CONTROL")
    feedme_quality_threshold: float = Field(default=0.7, alias="FEEDME_QUALITY_THRESHOLD")
    
    # Reasoning Engine Configuration
    reasoning_enable_chain_of_thought: bool = Field(default=True, alias="REASONING_ENABLE_CHAIN_OF_THOUGHT")
    reasoning_enable_problem_solving: bool = Field(default=True, alias="REASONING_ENABLE_PROBLEM_SOLVING")
    reasoning_enable_tool_intelligence: bool = Field(default=True, alias="REASONING_ENABLE_TOOL_INTELLIGENCE")
    reasoning_enable_quality_assessment: bool = Field(default=True, alias="REASONING_ENABLE_QUALITY_ASSESSMENT")
    reasoning_enable_reasoning_transparency: bool = Field(default=True, alias="REASONING_ENABLE_REASONING_TRANSPARENCY")
    reasoning_debug_mode: bool = Field(default=False, alias="REASONING_DEBUG_MODE")
    
    # Enhanced Log Analysis v3.0 Configuration
    log_analysis_use_optimized_analysis: bool = Field(default=True, alias="USE_OPTIMIZED_ANALYSIS")
    log_analysis_optimization_threshold_lines: int = Field(default=500, alias="OPTIMIZATION_THRESHOLD_LINES")
    log_analysis_enable_ml_pattern_discovery: bool = Field(default=True, alias="ENABLE_ML_PATTERN_DISCOVERY")
    log_analysis_enable_predictive_analysis: bool = Field(default=True, alias="ENABLE_PREDICTIVE_ANALYSIS")
    log_analysis_enable_correlation_analysis: bool = Field(default=True, alias="ENABLE_CORRELATION_ANALYSIS")
    log_analysis_enable_automated_remediation: bool = Field(default=False, alias="ENABLE_AUTOMATED_REMEDIATION")
    log_analysis_enable_cross_platform_support: bool = Field(default=True, alias="ENABLE_CROSS_PLATFORM_SUPPORT")
    log_analysis_enable_multi_language_support: bool = Field(default=True, alias="ENABLE_MULTI_LANGUAGE_SUPPORT")
    log_analysis_enable_dependency_analysis: bool = Field(default=True, alias="ENABLE_DEPENDENCY_ANALYSIS")
    log_analysis_enable_edge_case_handling: bool = Field(default=True, alias="ENABLE_EDGE_CASE_HANDLING")
    
    # Performance and Optimization Settings
    log_analysis_max_chunk_size: int = Field(default=5000, alias="LOG_ANALYSIS_MAX_CHUNK_SIZE")
    log_analysis_max_context_chars: int = Field(default=15000, alias="LOG_ANALYSIS_MAX_CONTEXT_CHARS")
    log_analysis_parallel_chunks: int = Field(default=3, alias="LOG_ANALYSIS_PARALLEL_CHUNKS")
    log_analysis_cache_ttl_hours: int = Field(default=1, alias="LOG_ANALYSIS_CACHE_TTL_HOURS")
    log_analysis_ml_confidence_threshold: float = Field(default=0.85, alias="ML_CONFIDENCE_THRESHOLD")
    log_analysis_correlation_threshold: float = Field(default=0.7, alias="CORRELATION_THRESHOLD")
    
    # Testing and Validation Settings
    log_analysis_enable_comprehensive_testing: bool = Field(default=False, alias="ENABLE_COMPREHENSIVE_TESTING")
    log_analysis_test_framework_enabled: bool = Field(default=False, alias="TEST_FRAMEWORK_ENABLED")
    log_analysis_validation_strict_mode: bool = Field(default=False, alias="VALIDATION_STRICT_MODE")
    
    # Chat Session Configuration
    max_sessions_per_agent: int = Field(default=5, alias="MAX_SESSIONS_PER_AGENT")
    chat_message_max_length: int = Field(default=10000, alias="CHAT_MESSAGE_MAX_LENGTH")
    chat_title_max_length: int = Field(default=255, alias="CHAT_TITLE_MAX_LENGTH")
    chat_session_cleanup_days: int = Field(default=30, alias="CHAT_SESSION_CLEANUP_DAYS")
    chat_enable_message_history: bool = Field(default=True, alias="CHAT_ENABLE_MESSAGE_HISTORY")
    chat_default_page_size: int = Field(default=10, alias="CHAT_DEFAULT_PAGE_SIZE")
    chat_max_page_size: int = Field(default=100, alias="CHAT_MAX_PAGE_SIZE")
    
    # Supabase Configuration
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    supabase_anon_key: Optional[str] = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_key: Optional[str] = Field(default=None, alias="SUPABASE_SERVICE_KEY")
    
    # Rate Limiting Configuration
    gemini_flash_rpm_limit: int = Field(default=8, alias="GEMINI_FLASH_RPM_LIMIT")
    gemini_flash_rpd_limit: int = Field(default=200, alias="GEMINI_FLASH_RPD_LIMIT")
    gemini_pro_rpm_limit: int = Field(default=4, alias="GEMINI_PRO_RPM_LIMIT")
    gemini_pro_rpd_limit: int = Field(default=80, alias="GEMINI_PRO_RPD_LIMIT")
    rate_limit_redis_url: str = Field(default="redis://localhost:6379", alias="RATE_LIMIT_REDIS_URL")
    rate_limit_redis_prefix: str = Field(default="mb_sparrow_rl", alias="RATE_LIMIT_REDIS_PREFIX")
    rate_limit_redis_db: int = Field(default=3, alias="RATE_LIMIT_REDIS_DB")
    circuit_breaker_enabled: bool = Field(default=True, alias="CIRCUIT_BREAKER_ENABLED")
    circuit_breaker_failure_threshold: int = Field(default=5, alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    circuit_breaker_timeout: int = Field(default=60, alias="CIRCUIT_BREAKER_TIMEOUT")
    rate_limit_safety_margin: float = Field(default=0.2, alias="RATE_LIMIT_SAFETY_MARGIN")
    rate_limit_monitoring_enabled: bool = Field(default=True, alias="RATE_LIMIT_MONITORING_ENABLED")
    circuit_breaker_success_threshold: int = Field(default=3, alias="CIRCUIT_BREAKER_SUCCESS_THRESHOLD")
    
    # JWT Configuration
    jwt_secret: str = Field(default="change-this-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_token_expire_minutes: int = Field(default=1440, alias="JWT_TOKEN_EXPIRE_MINUTES")  # 24 hours default

    @field_validator('feedme_max_pdf_size_mb')
    @classmethod
    def validate_feedme_max_pdf_size_mb(cls, v: int) -> int:
        """Validate that PDF size limit is within acceptable bounds"""
        MIN_PDF_SIZE_MB = 1
        MAX_PDF_SIZE_MB = 100  # Maximum 100MB for server capabilities
        
        if v < MIN_PDF_SIZE_MB:
            raise ValueError(f"feedme_max_pdf_size_mb must be at least {MIN_PDF_SIZE_MB} MB")
        
        if v > MAX_PDF_SIZE_MB:
            raise ValueError(f"feedme_max_pdf_size_mb must not exceed {MAX_PDF_SIZE_MB} MB for server capabilities")
        
        return v

    class Config:
        case_sensitive = False
        env_file = ENV_PATH
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    """
    Return a singleton instance of the application settings.
    
    Uses an internal cache to ensure the same Settings instance is returned on each call.
    """
    return Settings()

# Instantiate settings at import time for convenience
settings: Settings = get_settings()
