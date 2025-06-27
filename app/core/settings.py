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
    
    # FeedMe Configuration
    feedme_enabled: bool = Field(default=True, alias="FEEDME_ENABLED")
    feedme_html_enabled: bool = Field(default=True, alias="FEEDME_HTML_ENABLED")
    feedme_max_file_size_mb: int = Field(default=10, alias="FEEDME_MAX_FILE_SIZE_MB")
    feedme_max_examples_per_conversation: int = Field(default=20, alias="FEEDME_MAX_EXAMPLES_PER_CONVERSATION")
    feedme_embedding_batch_size: int = Field(default=10, alias="FEEDME_EMBEDDING_BATCH_SIZE")
    feedme_similarity_threshold: float = Field(default=0.7, alias="FEEDME_SIMILARITY_THRESHOLD")
    feedme_max_retrieval_results: int = Field(default=3, alias="FEEDME_MAX_RETRIEVAL_RESULTS")
    
    # FeedMe v2.0 Configuration
    feedme_min_db_connections: int = Field(default=2, alias="FEEDME_MIN_DB_CONNECTIONS")
    feedme_max_db_connections: int = Field(default=20, alias="FEEDME_MAX_DB_CONNECTIONS")
    feedme_db_timeout: int = Field(default=30, alias="FEEDME_DB_TIMEOUT")
    feedme_db_retry_attempts: int = Field(default=3, alias="FEEDME_DB_RETRY_ATTEMPTS")
    feedme_db_retry_delay: float = Field(default=1.0, alias="FEEDME_DB_RETRY_DELAY")
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
