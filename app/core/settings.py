from __future__ import annotations

import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
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

logger = logging.getLogger(__name__)

_RETRIEVAL_PRIMARY_ALLOWED = {"rpc", "store"}

class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ENV_PATH,
        extra="ignore",
    )

    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")

    # LangSmith tracing configuration
    langsmith_tracing_enabled: bool = Field(default=False, alias="LANGSMITH_TRACING_ENABLED")
    langsmith_api_key: Optional[str] = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_endpoint: Optional[str] = Field(default=None, alias="LANGSMITH_ENDPOINT")
    langsmith_project: Optional[str] = Field(default=None, alias="LANGSMITH_PROJECT")
    
    # In-Memory Session Store Configuration (replaces Redis for small deployments)
    session_store_max_sessions: int = Field(default=100, alias="SESSION_STORE_MAX_SESSIONS")
    session_store_default_ttl: int = Field(default=3600, alias="SESSION_STORE_DEFAULT_TTL")
    session_store_cleanup_interval: int = Field(default=300, alias="SESSION_STORE_CLEANUP_INTERVAL")
    
    # Legacy Redis configuration (kept for compatibility, not used in simplified deployment)
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    cache_ttl_sec: int = Field(default=3600, alias="CACHE_TTL_SEC")
    router_conf_threshold: float = Field(default=0.6, alias="ROUTER_CONF_THRESHOLD")
    router_model: str = Field(default="gemini-2.5-flash-lite", alias="ROUTER_MODEL")
    node_timeout_sec: float = Field(default=30.0, alias="NODE_TIMEOUT_SEC")
    use_enhanced_log_analysis: bool = Field(default=True, alias="USE_ENHANCED_LOG_ANALYSIS")
    enhanced_log_model: str = Field(default="gemini-2.5-pro", alias="ENHANCED_LOG_MODEL")
    # Provider/model selection for primary agent
    primary_agent_provider: str = Field(default="google", alias="PRIMARY_AGENT_PROVIDER")
    primary_agent_model: str = Field(default="gemini-2.5-flash", alias="PRIMARY_AGENT_MODEL")
    primary_agent_temperature: float = Field(default=0.2, alias="PRIMARY_AGENT_TEMPERATURE")
    primary_agent_thinking_budget: Optional[int] = Field(default=None, alias="THINKING_BUDGET")
    primary_agent_formatting: str = Field(default="natural", alias="PRIMARY_AGENT_FORMATTING")
    primary_agent_quality_level: str = Field(default="balanced", alias="PRIMARY_AGENT_QUALITY_LEVEL")
    primary_agent_prompt_version: str = Field(default="v10", alias="PRIMARY_AGENT_PROMPT_VERSION")
    enable_websearch: bool = Field(default=True, alias="ENABLE_WEBSEARCH")
    enable_grounded_responses: bool = Field(default=True, alias="ENABLE_GROUNDED_RESPONSES")
    primary_agent_min_kb_relevance: float = Field(default=0.65, alias="PRIMARY_AGENT_MIN_KB_RELEVANCE")
    primary_agent_min_kb_results: int = Field(default=1, alias="PRIMARY_AGENT_MIN_KB_RESULTS")
    reflection_default_provider: Optional[str] = Field(default=None, alias="DEFAULT_REFLECTION_PROVIDER")
    reflection_default_model: Optional[str] = Field(default=None, alias="DEFAULT_REFLECTION_MODEL")
    checkpointer_enabled: bool = Field(default=True, alias="ENABLE_CHECKPOINTER")
    checkpointer_db_url: Optional[str] = Field(default=None, alias="CHECKPOINTER_DB_URL")
    checkpointer_pool_size: int = Field(default=5, alias="CHECKPOINTER_POOL_SIZE")
    checkpointer_max_overflow: int = Field(default=10, alias="CHECKPOINTER_MAX_OVERFLOW")
    graph_viz_export_enabled: bool = Field(default=False, alias="ENABLE_GRAPH_VIZ_EXPORT")
    graph_viz_output_path: str = Field(
        default="docs/graphs/primary_agent_graph.mmd", alias="GRAPH_VIZ_OUTPUT_PATH"
    )
    
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
    feedme_max_tokens_per_minute: int = Field(default=250000, alias="FEEDME_MAX_TOKENS_PER_MINUTE")
    feedme_max_tokens_per_chunk: int = Field(default=8000, alias="FEEDME_MAX_TOKENS_PER_CHUNK")
    feedme_chunk_overlap_tokens: int = Field(default=500, alias="FEEDME_CHUNK_OVERLAP_TOKENS")
    
    # OCR Processing Configuration
    feedme_ocr_enabled: bool = Field(default=True, alias="FEEDME_OCR_ENABLED")
    feedme_ocr_confidence_threshold: float = Field(default=0.7, alias="FEEDME_OCR_CONFIDENCE_THRESHOLD")
    
    # Quality Control Configuration
    feedme_similarity_threshold: float = Field(default=0.7, alias="FEEDME_SIMILARITY_THRESHOLD")
    feedme_confidence_threshold: float = Field(default=0.7, alias="FEEDME_CONFIDENCE_THRESHOLD")
    feedme_async_processing: bool = Field(default=True, alias="FEEDME_ASYNC_PROCESSING")
    # Celery configuration (use Redis by default for multi-process workers)
    feedme_celery_broker: str = Field(default="redis://localhost:6379/1", alias="FEEDME_CELERY_BROKER")
    feedme_result_backend: str = Field(default="redis://localhost:6379/2", alias="FEEDME_RESULT_BACKEND")
    feedme_security_enabled: bool = Field(default=True, alias="FEEDME_SECURITY_ENABLED")
    feedme_rate_limit_per_minute: int = Field(default=15, alias="FEEDME_RATE_LIMIT_PER_MINUTE")
    feedme_requests_per_day_limit: int = Field(default=1000, alias="FEEDME_REQUESTS_PER_DAY_LIMIT")
    feedme_version_control: bool = Field(default=True, alias="FEEDME_VERSION_CONTROL")
    feedme_quality_threshold: float = Field(default=0.7, alias="FEEDME_QUALITY_THRESHOLD")
    
    # Reasoning Engine Configuration
    reasoning_enable_chain_of_thought: bool = Field(default=True, alias="REASONING_ENABLE_CHAIN_OF_THOUGHT")
    reasoning_enable_problem_solving: bool = Field(default=True, alias="REASONING_ENABLE_PROBLEM_SOLVING")
    reasoning_enable_tool_intelligence: bool = Field(default=True, alias="REASONING_ENABLE_TOOL_INTELLIGENCE")
    reasoning_enable_quality_assessment: bool = Field(default=True, alias="REASONING_ENABLE_QUALITY_ASSESSMENT")
    reasoning_enable_reasoning_transparency: bool = Field(default=True, alias="REASONING_ENABLE_REASONING_TRANSPARENCY")
    reasoning_debug_mode: bool = Field(default=False, alias="REASONING_DEBUG_MODE")
    reasoning_enable_thinking_trace: bool = Field(default=True, alias="ENABLE_THINKING_TRACE")

    # SSE Streaming Controls
    sse_prelude_size: int = Field(default=2048, alias="SSE_PRELUDE_SIZE")
    sse_heartbeat_interval: float = Field(default=5.0, alias="SSE_HEARTBEAT_INTERVAL")
    sse_heartbeat_comment: str = Field(default="ping", alias="SSE_HEARTBEAT_COMMENT")
    
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
    supabase_jwt_secret: Optional[str] = Field(default=None, alias="SUPABASE_JWT_SECRET")
    supabase_db_conn: Optional[str] = Field(default=None, alias="SUPABASE_DB_CONN")

    # Agent Memory Configuration
    enable_agent_memory: bool = Field(default=False, alias="ENABLE_AGENT_MEMORY")
    memory_backend: str = Field(default="supabase", alias="MEMORY_BACKEND")
    memory_collection_primary: str = Field(default="mem_primary", alias="MEMORY_COLLECTION_PRIMARY")
    memory_collection_logs: str = Field(default="mem_logs", alias="MEMORY_COLLECTION_LOGS")
    memory_top_k: int = Field(default=5, alias="MEMORY_TOP_K")
    memory_char_budget: int = Field(default=2000, alias="MEMORY_CHAR_BUDGET")
    memory_ttl_sec: int = Field(default=180, alias="MEMORY_TTL_SEC")
    memory_embed_provider: str = Field(default="gemini", alias="MEMORY_EMBED_PROVIDER")
    memory_embed_model: str = Field(default="models/gemini-embedding-001", alias="MEMORY_EMBED_MODEL")
    memory_embed_dims: int = Field(default=3072, alias="MEMORY_EMBED_DIMS")

    # FeedMe AI Configuration
    feedme_model_name: str = Field(default="gemini-2.5-flash-lite-preview-09-2025", alias="FEEDME_MODEL_NAME")
    feedme_ai_pdf_enabled: bool = Field(default=True, alias="FEEDME_AI_PDF_ENABLED")
    feedme_ai_max_pages: int = Field(default=10, alias="FEEDME_AI_MAX_PAGES")
    feedme_ai_pages_per_call: int = Field(default=3, alias="FEEDME_AI_PAGES_PER_CALL")
    feedme_max_pdf_size_mb: int = Field(default=50, alias="FEEDME_MAX_PDF_SIZE_MB")

    # Global Knowledge / Store integration (Phase 0)
    enable_global_knowledge_injection: bool = Field(
        default=False, alias="ENABLE_GLOBAL_KNOWLEDGE_INJECTION"
    )
    enable_store_adapter: bool = Field(default=False, alias="ENABLE_STORE_ADAPTER")
    enable_store_writes: bool = Field(default=False, alias="ENABLE_STORE_WRITES")
    retrieval_primary: str = Field(default="rpc", alias="RETRIEVAL_PRIMARY")
    global_store_db_uri: Optional[str] = Field(default=None, alias="GLOBAL_STORE_DB_URI")
    global_knowledge_top_k: int = Field(default=6, alias="GLOBAL_KNOWLEDGE_TOP_K")
    global_knowledge_max_chars: int = Field(default=1600, alias="GLOBAL_KNOWLEDGE_MAX_CHARS")
    global_knowledge_min_relevance: float = Field(default=0.2, alias="GLOBAL_KNOWLEDGE_MIN_RELEVANCE")
    global_knowledge_adapter_min_similarity: float = Field(default=0.15, alias="GLOBAL_KNOWLEDGE_ADAPTER_MIN_SIMILARITY")
    global_knowledge_adapter_min_query_length: int = Field(default=12, alias="GLOBAL_KNOWLEDGE_ADAPTER_MIN_QUERY_LENGTH")
    global_knowledge_adapter_max_results: int = Field(default=6, alias="GLOBAL_KNOWLEDGE_ADAPTER_MAX_RESULTS")
    global_knowledge_enable_adapter_fallback: bool = Field(default=True, alias="GLOBAL_KNOWLEDGE_ENABLE_ADAPTER_FALLBACK")
    
    # Rate Limiting Configuration (free tier defaults; override via env)
    gemini_flash_rpm_limit: int = Field(default=15, alias="GEMINI_FLASH_RPM_LIMIT")
    gemini_flash_rpd_limit: int = Field(default=1000, alias="GEMINI_FLASH_RPD_LIMIT")
    gemini_pro_rpm_limit: int = Field(default=5, alias="GEMINI_PRO_RPM_LIMIT")
    gemini_pro_rpd_limit: int = Field(default=100, alias="GEMINI_PRO_RPD_LIMIT")

    # Application-level usage budgets
    primary_agent_daily_budget: int = Field(default=500, alias="PRIMARY_AGENT_DAILY_BUDGET")
    router_daily_budget: int = Field(default=300, alias="ROUTER_DAILY_BUDGET")
    
    # Gemini Embeddings Configuration
    gemini_embed_model: str = Field(default="models/gemini-embedding-001", alias="GEMINI_EMBED_MODEL")
    gemini_embed_rpm_limit: int = Field(default=100, alias="GEMINI_EMBED_RPM_LIMIT")
    gemini_embed_tpm_limit: int = Field(default=30000, alias="GEMINI_EMBED_TPM_LIMIT")
    gemini_embed_rpd_limit: int = Field(default=1000, alias="GEMINI_EMBED_RPD_LIMIT")
    # Simplified rate limiting - uses in-memory tracking instead of Redis
    rate_limit_use_memory: bool = Field(default=True, alias="RATE_LIMIT_USE_MEMORY")
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
    # Do not ship default secrets; require explicit configuration via environment
    jwt_secret_key: Optional[str] = Field(default=None, alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=30, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # API Key Encryption
    # No hardcoded default; set via env only. In dev without FORCE_PRODUCTION_SECURITY, a derived ephemeral key will be used.
    api_key_encryption_secret: Optional[str] = Field(default=None, alias="API_KEY_ENCRYPTION_SECRET")
    
    # Authentication
    skip_auth: bool = Field(default=False, alias="SKIP_AUTH")
    # Use a valid UUID for development (this is a v4 UUID)
    development_user_id: str = Field(default="00000000-0000-0000-0000-000000000000", alias="DEVELOPMENT_USER_ID")
    
    @field_validator('skip_auth', mode='before')
    @classmethod
    def parse_skip_auth(cls, v):
        """Parse boolean from string environment variable."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            # Handle string values from environment
            return v.lower() in ('true', '1', 'yes', 'on')
        return False
    
    # Security Feature Toggles
    enable_auth_endpoints: bool = Field(default=True, alias="ENABLE_AUTH_ENDPOINTS")
    enable_api_key_endpoints: bool = Field(default=True, alias="ENABLE_API_KEY_ENDPOINTS")
    force_production_security: bool = Field(default=True, alias="FORCE_PRODUCTION_SECURITY")

    # Legacy endpoints gating removed: no legacy endpoints remain
    
    # Production Environment Configuration
    production_domains: List[str] = Field(
        default=["supabase.co"], 
        alias="PRODUCTION_DOMAINS"
    )
    
    # Internal API Security
    internal_api_token: Optional[str] = Field(default=None, alias="INTERNAL_API_TOKEN")

    # OAuth Email Domain Restrictions
    # Comma-separated list of allowed email domains for OAuth (e.g., "getmailbird.com,example.org")
    # In production, only emails from these domains will be accepted after OAuth sign-in.
    allowed_oauth_email_domains: List[str] = Field(
        default=["getmailbird.com"], alias="ALLOWED_OAUTH_EMAIL_DOMAINS"
    )

    # Zendesk Integration (webhook + 30m batch posting, no backfill)
    zendesk_enabled: bool = Field(default=False, alias="ZENDESK_ENABLED")
    zendesk_subdomain: Optional[str] = Field(default=None, alias="ZENDESK_SUBDOMAIN")
    zendesk_email: Optional[str] = Field(default=None, alias="ZENDESK_EMAIL")
    zendesk_api_token: Optional[str] = Field(default=None, alias="ZENDESK_API_TOKEN")
    zendesk_signing_secret: Optional[str] = Field(default=None, alias="ZENDESK_SIGNING_SECRET")
    zendesk_brand_id: Optional[str] = Field(default=None, alias="ZENDESK_BRAND_ID")
    zendesk_dry_run: bool = Field(default=True, alias="ZENDESK_DRY_RUN")
    zendesk_poll_interval_sec: int = Field(default=60, alias="ZENDESK_POLL_INTERVAL_SEC")
    zendesk_rpm_limit: int = Field(default=300, alias="ZENDESK_RPM_LIMIT")
    zendesk_monthly_api_budget: int = Field(default=350, alias="ZENDESK_MONTHLY_API_BUDGET")
    zendesk_gemini_daily_limit: int = Field(default=1000, alias="ZENDESK_GEMINI_DAILY_LIMIT")
    zendesk_max_retries: int = Field(default=5, alias="ZENDESK_MAX_RETRIES")
    zendesk_queue_retention_days: int = Field(default=30, alias="ZENDESK_QUEUE_RETENTION_DAYS")
    # Debug: enable limited verification logs for Zendesk HMAC (do NOT enable in prod)
    zendesk_debug_verify: bool = Field(default=False, alias="ZENDESK_DEBUG_VERIFY")
    # Use HTML notes in Zendesk for better readability (fallback to text on failure)
    zendesk_use_html: bool = Field(default=True, alias="ZENDESK_USE_HTML")
    # Formatting style for paragraph sentence breaks in HTML mode: compact|relaxed
    zendesk_format_style: str = Field(default="compact", alias="ZENDESK_FORMAT_STYLE")

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

    @field_validator('api_key_encryption_secret')
    @classmethod
    def validate_api_key_encryption_secret(cls, v: str) -> str:
        """Validate that API key encryption secret is at least 32 bytes when UTF-8 encoded.
        Allow None so that development environments can derive an ephemeral key instead of shipping a default secret.
        """
        if v is None:
            return v
        if len(v.encode('utf-8')) < 32:
            raise ValueError("api_key_encryption_secret must be at least 32 bytes long when UTF-8 encoded")
        return v

    @field_validator('primary_agent_min_kb_relevance')
    @classmethod
    def validate_primary_agent_min_kb_relevance(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("primary_agent_min_kb_relevance must be between 0.0 and 1.0")
        return v

    @field_validator('primary_agent_min_kb_results')
    @classmethod
    def validate_primary_agent_min_kb_results(cls, v: int) -> int:
        if v < 0:
            raise ValueError("primary_agent_min_kb_results must be zero or greater")
        return v

    @field_validator("primary_agent_temperature")
    @classmethod
    def validate_primary_agent_temperature(cls, value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("primary_agent_temperature must be between 0.0 and 2.0")
        return value

    @field_validator("primary_agent_thinking_budget")
    @classmethod
    def validate_primary_agent_thinking_budget(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if value < -1:
            raise ValueError("primary_agent_thinking_budget must be -1 (dynamic) or non-negative")
        return value

    @field_validator("primary_agent_formatting")
    @classmethod
    def validate_primary_agent_formatting(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"natural", "strict", "lean"}:
            raise ValueError("primary_agent_formatting must be one of: natural, strict, lean")
        return normalized

    @field_validator("retrieval_primary", mode="before")
    @classmethod
    def validate_retrieval_primary(cls, value: str | None) -> str:
        """Normalize retrieval primary selector and fallback to rpc when invalid."""
        if value is None:
            return "rpc"
        normalized = str(value).strip().lower()
        if normalized not in _RETRIEVAL_PRIMARY_ALLOWED:
            logger.warning(
                "Invalid retrieval_primary '%s' provided; expected one of %s. Falling back to 'rpc'.",
                value,
                sorted(_RETRIEVAL_PRIMARY_ALLOWED),
            )
            return "rpc"
        return normalized

    @field_validator("global_knowledge_top_k")
    @classmethod
    def validate_global_knowledge_top_k(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("global_knowledge_top_k must be greater than zero")
        return value

    @field_validator("global_knowledge_max_chars")
    @classmethod
    def validate_global_knowledge_max_chars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("global_knowledge_max_chars must be greater than zero")
        return value

    @field_validator("memory_top_k")
    @classmethod
    def validate_memory_top_k(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory_top_k must be greater than zero")
        return value

    @field_validator("memory_char_budget")
    @classmethod
    def validate_memory_char_budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory_char_budget must be greater than zero")
        return value

    @field_validator("memory_ttl_sec")
    @classmethod
    def validate_memory_ttl_sec(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory_ttl_sec must be greater than zero")
        return value

    @field_validator("memory_embed_dims")
    @classmethod
    def validate_memory_embed_dims(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory_embed_dims must be greater than zero")
        return value

    @field_validator('zendesk_poll_interval_sec')
    @classmethod
    def validate_zendesk_poll_interval(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("zendesk_poll_interval_sec must be positive")
        return v

    @field_validator('zendesk_rpm_limit', 'zendesk_monthly_api_budget', 'zendesk_gemini_daily_limit', 'zendesk_max_retries')
    @classmethod
    def validate_zendesk_limits(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Zendesk limits must be positive integers")
        return v

    @field_validator('zendesk_queue_retention_days')
    @classmethod
    def validate_zendesk_retention(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("zendesk_queue_retention_days must be positive")
        return v

    def is_production_mode(self) -> bool:
        """
        Determine if we're running in production mode.
        Production mode is detected by:
        1. FORCE_PRODUCTION_SECURITY=true, or
        2. Environment indicators like ENVIRONMENT=production, DEPLOY_ENV=prod, etc.
        """
        # Check explicit production security flag
        if self.force_production_security:
            return True
            
        # Check common production environment variables
        env_indicators = [
            os.getenv("ENVIRONMENT", "").lower() in ["production", "prod"],
            os.getenv("DEPLOY_ENV", "").lower() in ["production", "prod"],
            os.getenv("NODE_ENV", "").lower() == "production",
            os.getenv("STAGE", "").lower() in ["production", "prod"],
            # Check if we have production-like database URLs using configurable domains
            self._is_production_database_url(),
        ]
        
        return any(env_indicators)

    @field_validator('allowed_oauth_email_domains', mode='before')
    @classmethod
    def parse_allowed_domains(cls, v):
        """Parse env into a normalized list of domains."""
        if v is None:
            return []
        if isinstance(v, str):
            return [d.strip().lower() for d in v.split(',') if d and d.strip()]
        if isinstance(v, list):
            return [str(d).strip().lower() for d in v if str(d).strip()]
        return []

    def is_email_domain_allowed(self, email: Optional[str]) -> bool:
        """Return True if email's domain is in the allowed list (or list is empty)."""
        if not email:
            return False
        try:
            domain = email.split('@')[-1].strip().lower()
        except Exception:
            return False
        allowed = [d.strip().lower() for d in (self.allowed_oauth_email_domains or []) if d]
        # If list provided, enforce it. If empty (misconfigured), deny by default in prod.
        if self.is_production_mode():
            return domain in allowed if allowed else False
        # In non-prod, allow if list empty; otherwise enforce
        return True if not allowed else domain in allowed
    
    def _is_production_database_url(self) -> bool:
        """
        Check if the database URL indicates a production environment
        using configurable production domains.
        """
        if not self.supabase_url:
            return False
            
        return any(domain in self.supabase_url for domain in self.production_domains)
    
    def _should_enable_security_endpoint(self, flag: bool) -> bool:
        """
        Helper method to determine if a security endpoint should be enabled.
        Returns True if in production mode or the flag is True.
        """
        if self.is_production_mode():
            return True  # Always enable in production
        return flag
    
    def should_enable_auth_endpoints(self) -> bool:
        """
        Determine if authentication endpoints should be enabled.
        Auth endpoints are enabled unless explicitly disabled AND not in production.
        """
        return self._should_enable_security_endpoint(self.enable_auth_endpoints)
    
    def should_enable_api_key_endpoints(self) -> bool:
        """
        Determine if API key endpoints should be enabled.
        API key endpoints are enabled unless explicitly disabled AND not in production.
        """
        return self._should_enable_security_endpoint(self.enable_api_key_endpoints)
    
    # Removed: legacy_endpoints_enabled()
    
    def should_enable_thinking_trace(self) -> bool:
        """
        Helper method to determine if thinking trace should be enabled.
        Returns False in production mode, otherwise returns the value of reasoning_enable_thinking_trace.
        """
        if self.is_production_mode():
            return False
        return self.reasoning_enable_thinking_trace

    def should_enable_global_knowledge(self) -> bool:
        """Return True when global knowledge injection is enabled."""
        return bool(self.enable_global_knowledge_injection)

    def should_use_store_adapter(self) -> bool:
        """Determine if the store adapter should be leveraged for retrieval operations."""
        return bool(self.enable_store_adapter) and self.retrieval_primary == "store"

    def should_enable_store_writes(self) -> bool:
        """Determine if writing to the global store is permitted."""
        return bool(self.enable_store_writes)

    def get_retrieval_primary(self) -> str:
        """Return the normalized retrieval primary selector."""
        return self.retrieval_primary

    def has_global_store_configuration(self) -> bool:
        """Return True when a global store connection string is configured."""
        return bool(self.global_store_db_uri)

    def should_use_adapter_fallback(self, *, top_k: int, store_hits: int, query_len: int) -> bool:
        """Determine whether the adapter fallback should run for global knowledge."""
        if not self.global_knowledge_enable_adapter_fallback:
            return False
        if store_hits >= max(1, top_k):
            return False
        if query_len < max(0, self.global_knowledge_adapter_min_query_length):
            return False
        if not (self.enable_store_adapter or self.get_retrieval_primary() == "rpc"):
            return False
        return True

    def memory_backend_is_supabase(self) -> bool:
        """Return True when the memory backend is Supabase."""
        return str(self.memory_backend or "").strip().lower() == "supabase"

    def should_enable_agent_memory(self) -> bool:
        """Evaluate if the agent memory layer should be enabled."""
        if not self.enable_agent_memory:
            return False
        if not self.memory_backend_is_supabase():
            return False
        return bool(self.supabase_db_conn)

    def get_memory_connection_string(self) -> Optional[str]:
        """Return the connection string for the memory backend, if configured."""
        return self.supabase_db_conn

    def get_memory_collections(self) -> Dict[str, str]:
        """Return configured memory collections."""
        return {
            "primary": self.memory_collection_primary,
            "logs": self.memory_collection_logs,
        }


@lru_cache()
def get_settings() -> Settings:
    """
    Return a singleton instance of the application settings.
    
    Uses an internal cache to ensure the same Settings instance is returned on each call.
    """
    return Settings()

# Instantiate settings at import time for convenience
settings: Settings = get_settings()
