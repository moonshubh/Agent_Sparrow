from __future__ import annotations

import json
import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, model_validator

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
ENV_LOCAL_PATH = project_root / ".env.local"

# Load .env first, then .env.local to allow overrides
load_dotenv(ENV_PATH)
load_dotenv(ENV_LOCAL_PATH, override=True)  # .env.local overrides .env

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=ENV_PATH,
        extra="ignore",
    )

    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    @model_validator(mode="after")
    def hydrate_gemini_api_key(self) -> "Settings":
        # Backwards/ops compatibility: some environments still use GOOGLE_API_KEY
        # for Gemini. Prefer GEMINI_API_KEY when present.
        if not self.gemini_api_key and self.google_api_key:
            self.gemini_api_key = self.google_api_key
        return self

    @model_validator(mode="after")
    def hydrate_minimax_base_url(self) -> "Settings":
        # Keep Minimax base URL aligned with API host when host is customized.
        default_host = "https://api.minimax.io"
        default_base = "https://api.minimax.io/v1"
        if self.minimax_api_host.rstrip("/") != default_host:
            if self.minimax_base_url == default_base:
                self.minimax_base_url = f"{self.minimax_api_host.rstrip('/')}/v1"
        return self

    # XAI/Grok Configuration
    xai_api_key: Optional[str] = Field(default=None, alias="XAI_API_KEY")
    xai_reasoning_enabled: bool = Field(default=True, alias="XAI_REASONING_ENABLED")

    # OpenRouter Configuration
    openrouter_api_key: Optional[str] = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_app_name: str = Field(default="Agent Sparrow", alias="OPENROUTER_APP_NAME")
    openrouter_referer: Optional[str] = Field(default=None, alias="OPENROUTER_REFERER")

    # Minimax Configuration (uses OpenRouter code path with Minimax API)
    minimax_api_key: Optional[str] = Field(default=None, alias="MINIMAX_API_KEY")
    # Optional separate key for Minimax Coding Plan (MCP tools).
    minimax_coding_plan_api_key: Optional[str] = Field(
        default=None, alias="MINIMAX_CODING_PLAN_API_KEY"
    )
    minimax_base_url: str = Field(default="https://api.minimax.io/v1", alias="MINIMAX_BASE_URL")
    minimax_api_host: str = Field(default="https://api.minimax.io", alias="MINIMAX_API_HOST")
    minimax_mcp_command: str = Field(default="python", alias="MINIMAX_MCP_COMMAND")
    minimax_mcp_args: str = Field(
        default="-m minimax_mcp.server", alias="MINIMAX_MCP_ARGS"
    )

    # LangSmith tracing configuration
    langsmith_tracing_enabled: bool = Field(default=False, alias="LANGSMITH_TRACING_ENABLED")
    langsmith_api_key: Optional[str] = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_endpoint: Optional[str] = Field(default=None, alias="LANGSMITH_ENDPOINT")
    langsmith_project: Optional[str] = Field(default=None, alias="LANGSMITH_PROJECT")
    
    # In-Memory Session Store Configuration (replaces Redis for small deployments)
    session_store_max_sessions: int = Field(default=100, alias="SESSION_STORE_MAX_SESSIONS")
    session_store_default_ttl: int = Field(default=3600, alias="SESSION_STORE_DEFAULT_TTL")
    session_store_cleanup_interval: int = Field(default=300, alias="SESSION_STORE_CLEANUP_INTERVAL")

    # Workspace retention (Phase 1: keep N sessions per user)
    workspace_max_sessions_per_user: int = Field(default=10, alias="WORKSPACE_MAX_SESSIONS_PER_USER")
    workspace_prune_sessions_enabled: bool = Field(default=True, alias="WORKSPACE_PRUNE_SESSIONS_ENABLED")

    # Subagent workspace bridge (Phase 1)
    subagent_workspace_bridge_enabled: bool = Field(default=True, alias="SUBAGENT_WORKSPACE_BRIDGE_ENABLED")
    subagent_report_read_limit_chars: int = Field(default=20000, alias="SUBAGENT_REPORT_READ_LIMIT_CHARS")
    subagent_context_capsule_max_chars: int = Field(default=12000, alias="SUBAGENT_CONTEXT_CAPSULE_MAX_CHARS")
    # When enabled, allow the coordinator to delegate additional work to an implicit
    # general-purpose subagent (best effort, usually routed to Minimax when available).
    subagent_general_purpose_enabled: bool = Field(
        default=True,
        alias="SUBAGENT_GENERAL_PURPOSE_ENABLED",
    )
    subagent_allow_unverified_models: bool = Field(
        default=False,
        alias="SUBAGENT_ALLOW_UNVERIFIED_MODELS",
    )
    
    # Legacy Redis configuration (kept for compatibility, not used in simplified deployment)
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    cache_ttl_sec: int = Field(default=3600, alias="CACHE_TTL_SEC")
    router_conf_threshold: float = Field(default=0.6, alias="ROUTER_CONF_THRESHOLD")

    # Gemini Search Grounding configuration
    enable_grounding_search: bool = Field(default=False, alias="ENABLE_GROUNDING_SEARCH")
    grounding_max_results: int = Field(default=5, alias="GROUNDING_MAX_RESULTS")
    grounding_timeout_sec: float = Field(default=10.0, alias="GROUNDING_TIMEOUT_SEC")
    grounding_snippet_chars: int = Field(default=480, alias="GROUNDING_SNIPPET_CHARS")
    grounding_minute_limit: int = Field(default=30, alias="GROUNDING_MINUTE_LIMIT")
    grounding_daily_limit: int = Field(default=1000, alias="GROUNDING_DAILY_LIMIT")

    # MCP (Model Context Protocol) Configuration for Firecrawl
    firecrawl_mcp_enabled: bool = Field(default=True, alias="FIRECRAWL_MCP_ENABLED")
    firecrawl_mcp_endpoint: str = Field(
        default="https://mcp.firecrawl.dev/{FIRECRAWL_API_KEY}/v2/mcp",
        alias="FIRECRAWL_MCP_ENDPOINT",
    )
    firecrawl_api_key: Optional[str] = Field(default=None, alias="FIRECRAWL_API_KEY")
    firecrawl_default_max_age_ms: int = Field(default=172800000, alias="FIRECRAWL_DEFAULT_MAX_AGE_MS")  # 48 hours
    firecrawl_default_timeout_sec: float = Field(default=60.0, alias="FIRECRAWL_DEFAULT_TIMEOUT_SEC")
    firecrawl_rate_limit_rpm: int = Field(default=60, alias="FIRECRAWL_RATE_LIMIT_RPM")

    # Enhanced Tavily Configuration
    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    tavily_default_search_depth: str = Field(default="advanced", alias="TAVILY_DEFAULT_SEARCH_DEPTH")
    tavily_default_max_results: int = Field(default=10, alias="TAVILY_DEFAULT_MAX_RESULTS")
    tavily_include_images: bool = Field(default=True, alias="TAVILY_INCLUDE_IMAGES")

    node_timeout_sec: float = Field(default=30.0, alias="NODE_TIMEOUT_SEC")
    use_enhanced_log_analysis: bool = Field(default=True, alias="USE_ENHANCED_LOG_ANALYSIS")
    primary_agent_temperature: float = Field(default=0.2, alias="PRIMARY_AGENT_TEMPERATURE")
    primary_agent_thinking_budget: Optional[int] = Field(default=None, alias="THINKING_BUDGET")
    primary_agent_formatting: str = Field(default="natural", alias="PRIMARY_AGENT_FORMATTING")
    primary_agent_quality_level: str = Field(default="balanced", alias="PRIMARY_AGENT_QUALITY_LEVEL")
    primary_agent_prompt_version: str = Field(default="v10", alias="PRIMARY_AGENT_PROMPT_VERSION")
    # Thinking trace mode: narrated | hybrid | provider_reasoning | off
    trace_mode: str = Field(default="narrated", alias="TRACE_MODE")

    @field_validator("trace_mode")
    @classmethod
    def validate_trace_mode(cls, value: str) -> str:
        allowed = {"narrated", "hybrid", "provider_reasoning", "off"}
        normalized = (value or "narrated").lower().strip()
        return normalized if normalized in allowed else "narrated"

    enable_websearch: bool = Field(default=True, alias="ENABLE_WEBSEARCH")
    enable_grounded_responses: bool = Field(default=True, alias="ENABLE_GROUNDED_RESPONSES")
    primary_agent_min_kb_relevance: float = Field(default=0.65, alias="PRIMARY_AGENT_MIN_KB_RELEVANCE")
    primary_agent_min_kb_results: int = Field(default=1, alias="PRIMARY_AGENT_MIN_KB_RESULTS")
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
    feedme_max_pdf_size_mb: int = Field(default=50, alias="FEEDME_MAX_PDF_SIZE_MB")
    feedme_pdf_processing_timeout: int = Field(default=30, alias="FEEDME_PDF_PROCESSING_TIMEOUT")
    feedme_pdf_concurrent_limit: int = Field(default=5, alias="FEEDME_PDF_CONCURRENT_LIMIT")
    
    # Enhanced PDF Processing Configuration
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
    agent_memory_default_enabled: bool = Field(
        default=False,
        alias="AGENT_MEMORY_DEFAULT_ENABLED",
    )
    memory_backend: str = Field(default="supabase", alias="MEMORY_BACKEND")
    memory_collection_primary: str = Field(default="mem_primary", alias="MEMORY_COLLECTION_PRIMARY")
    memory_collection_logs: str = Field(default="mem_logs", alias="MEMORY_COLLECTION_LOGS")
    memory_top_k: int = Field(default=5, alias="MEMORY_TOP_K")
    memory_char_budget: int = Field(default=2000, alias="MEMORY_CHAR_BUDGET")
    memory_ttl_sec: int = Field(default=180, alias="MEMORY_TTL_SEC")
    memory_llm_inference: bool = Field(default=True, alias="MEMORY_LLM_INFERENCE")

    # Memory UI (Phase 3+) - capture and retrieval toggles
    enable_memory_ui_capture: bool = Field(default=False, alias="ENABLE_MEMORY_UI_CAPTURE")
    enable_memory_ui_retrieval: bool = Field(default=False, alias="ENABLE_MEMORY_UI_RETRIEVAL")
    memory_ui_agent_id: str = Field(default="sparrow", alias="MEMORY_UI_AGENT_ID")
    memory_ui_tenant_id: str = Field(default="mailbot", alias="MEMORY_UI_TENANT_ID")

    # FeedMe AI Configuration
    feedme_ai_pdf_enabled: bool = Field(default=True, alias="FEEDME_AI_PDF_ENABLED")
    feedme_ai_max_pages: int = Field(default=10, alias="FEEDME_AI_MAX_PAGES")
    feedme_ai_pages_per_call: int = Field(default=3, alias="FEEDME_AI_PAGES_PER_CALL")

    # Application-level usage budgets
    primary_agent_daily_budget: int = Field(default=500, alias="PRIMARY_AGENT_DAILY_BUDGET")
    router_daily_budget: int = Field(default=300, alias="ROUTER_DAILY_BUDGET")
    
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
    # Exclusion rules to prevent generating internal notes on certain tickets.
    # Example use-case: skip proactive feature-delivery tickets that are created already solved.
    zendesk_excluded_statuses: List[str] = Field(
        default_factory=lambda: ["solved", "closed"],
        alias="ZENDESK_EXCLUDED_STATUSES",
    )
    zendesk_excluded_tags: List[str] = Field(
        default_factory=lambda: ["mac_general__feature_delivered", "mb_spam_suspected"],
        alias="ZENDESK_EXCLUDED_TAGS",
    )
    zendesk_excluded_brand_ids: List[str] = Field(
        default_factory=list,
        alias="ZENDESK_EXCLUDED_BRAND_IDS",
    )
    zendesk_windows_brand_ids: List[str] = Field(default_factory=list, alias="ZENDESK_WINDOWS_BRAND_IDS")
    zendesk_dry_run: bool = Field(default=True, alias="ZENDESK_DRY_RUN")
    zendesk_poll_interval_sec: int = Field(default=60, alias="ZENDESK_POLL_INTERVAL_SEC")
    zendesk_rpm_limit: int = Field(default=240, alias="ZENDESK_RPM_LIMIT")
    zendesk_import_rpm_limit: int = Field(default=10, alias="ZENDESK_IMPORT_RPM_LIMIT")
    zendesk_monthly_api_budget: int = Field(default=0, alias="ZENDESK_MONTHLY_API_BUDGET")
    zendesk_gemini_daily_limit: int = Field(default=380, alias="ZENDESK_GEMINI_DAILY_LIMIT")
    zendesk_max_retries: int = Field(default=5, alias="ZENDESK_MAX_RETRIES")
    zendesk_queue_retention_days: int = Field(default=30, alias="ZENDESK_QUEUE_RETENTION_DAYS")
    # Optional: prefetch web context (Firecrawl/Tavily) when internal sources are insufficient
    zendesk_web_prefetch_enabled: bool = Field(default=True, alias="ZENDESK_WEB_PREFETCH_ENABLED")
    zendesk_web_prefetch_pages: int = Field(default=3, alias="ZENDESK_WEB_PREFETCH_PAGES")
    zendesk_firecrawl_enhanced_enabled: bool = Field(default=True, alias="ZENDESK_FIRECRAWL_ENHANCED_ENABLED")
    zendesk_firecrawl_support_domains: List[str] = Field(
        default_factory=lambda: [
            "https://support.getmailbird.com",
            "https://www.getmailbird.com/help",
        ],
        alias="ZENDESK_FIRECRAWL_SUPPORT_DOMAINS",
    )
    zendesk_firecrawl_support_pages: int = Field(default=3, alias="ZENDESK_FIRECRAWL_SUPPORT_PAGES")
    zendesk_firecrawl_support_screenshots: bool = Field(default=False, alias="ZENDESK_FIRECRAWL_SUPPORT_SCREENSHOTS")
    # Query Agent (Phase 1 context engineering)
    zendesk_query_agent_enabled: bool = Field(default=True, alias="ZENDESK_QUERY_AGENT_ENABLED")
    zendesk_query_agent_model: str = Field(default="gemini-2.5-flash", alias="ZENDESK_QUERY_AGENT_MODEL")
    zendesk_query_reformulation_max_attempts: int = Field(
        default=2, alias="ZENDESK_QUERY_REFORMULATION_MAX_ATTEMPTS"
    )
    zendesk_query_confidence_threshold: float = Field(default=0.6, alias="ZENDESK_QUERY_CONFIDENCE_THRESHOLD")
    zendesk_query_expansion_count: int = Field(default=2, alias="ZENDESK_QUERY_EXPANSION_COUNT")
    # Query decomposition for multi-issue tickets (Phase 2 context engineering)
    zendesk_query_decomposition_enabled: bool = Field(
        default=True, alias="ZENDESK_QUERY_DECOMPOSITION_ENABLED"
    )
    zendesk_query_decomposition_max_subqueries: int = Field(
        default=3, alias="ZENDESK_QUERY_DECOMPOSITION_MAX_SUBQUERIES"
    )
    # Complexity detection (Phase 2 context engineering)
    zendesk_complexity_threshold: float = Field(default=0.5, alias="ZENDESK_COMPLEXITY_THRESHOLD")
    # Retrieval tuning for macro/KB/FeedMe preflight
    zendesk_internal_retrieval_min_relevance: float = Field(default=0.35, alias="ZENDESK_INTERNAL_RETRIEVAL_MIN_RELEVANCE")
    zendesk_internal_retrieval_max_per_source: int = Field(default=3, alias="ZENDESK_INTERNAL_RETRIEVAL_MAX_PER_SOURCE")
    zendesk_macro_min_relevance: float = Field(default=0.55, alias="ZENDESK_MACRO_MIN_RELEVANCE")
    zendesk_feedme_min_relevance: float = Field(default=0.45, alias="ZENDESK_FEEDME_MIN_RELEVANCE")
    # Quality-first retrieval (Phase 3 context engineering)
    zendesk_quality_first_retrieval_enabled: bool = Field(
        default=True, alias="ZENDESK_QUALITY_FIRST_RETRIEVAL_ENABLED"
    )
    zendesk_rerank_enabled: bool = Field(default=True, alias="ZENDESK_RERANK_ENABLED")
    zendesk_rerank_model: str = Field(default="gemini-2.5-flash", alias="ZENDESK_RERANK_MODEL")
    zendesk_rerank_timeout_sec: int = Field(default=180, alias="ZENDESK_RERANK_TIMEOUT_SEC")
    zendesk_clash_detection_enabled: bool = Field(
        default=True, alias="ZENDESK_CLASH_DETECTION_ENABLED"
    )
    zendesk_clash_resolution: str = Field(default="prefer_newer", alias="ZENDESK_CLASH_RESOLUTION")
    zendesk_context_budget_tokens: int = Field(default=8000, alias="ZENDESK_CONTEXT_BUDGET_TOKENS")
    zendesk_confidence_high_threshold: float = Field(default=0.8, alias="ZENDESK_CONFIDENCE_HIGH_THRESHOLD")
    zendesk_confidence_low_threshold: float = Field(default=0.6, alias="ZENDESK_CONFIDENCE_LOW_THRESHOLD")
    # Output validation (Phase 4 context engineering)
    zendesk_output_validation_enabled: bool = Field(
        default=True, alias="ZENDESK_OUTPUT_VALIDATION_ENABLED"
    )
    zendesk_output_validation_max_rewrites: int = Field(
        default=1, alias="ZENDESK_OUTPUT_VALIDATION_MAX_REWRITES"
    )
    zendesk_drift_guard_enabled: bool = Field(default=True, alias="ZENDESK_DRIFT_GUARD_ENABLED")
    zendesk_drift_guard_strictness: str = Field(
        default="medium", alias="ZENDESK_DRIFT_GUARD_STRICTNESS"
    )
    # Advanced retrieval (Phase 6 context engineering)
    zendesk_feedme_slice_hydration_enabled: bool = Field(
        default=True, alias="ZENDESK_FEEDME_SLICE_HYDRATION_ENABLED"
    )
    zendesk_feedme_slice_window_before: int = Field(
        default=1, alias="ZENDESK_FEEDME_SLICE_WINDOW_BEFORE"
    )
    zendesk_feedme_slice_window_after: int = Field(
        default=1, alias="ZENDESK_FEEDME_SLICE_WINDOW_AFTER"
    )
    zendesk_feedme_slice_max_chunks: int = Field(
        default=8, alias="ZENDESK_FEEDME_SLICE_MAX_CHUNKS"
    )
    zendesk_source_specific_chunking_enabled: bool = Field(
        default=True, alias="ZENDESK_SOURCE_SPECIFIC_CHUNKING_ENABLED"
    )
    # Pattern-based context engineering (IssueResolutionStore + playbook learning)
    zendesk_issue_pattern_max_hits: int = Field(default=5, alias="ZENDESK_ISSUE_PATTERN_MAX_HITS")
    zendesk_issue_pattern_min_similarity: float = Field(default=0.62, alias="ZENDESK_ISSUE_PATTERN_MIN_SIMILARITY")
    zendesk_issue_pattern_learning_enabled: bool = Field(default=True, alias="ZENDESK_ISSUE_PATTERN_LEARNING_ENABLED")
    zendesk_playbook_learning_enabled: bool = Field(default=True, alias="ZENDESK_PLAYBOOK_LEARNING_ENABLED")
    zendesk_nature_field_id: Optional[str] = Field(default=None, alias="ZENDESK_NATURE_FIELD_ID")
    zendesk_nature_field_ids: List[str] = Field(default_factory=list, alias="ZENDESK_NATURE_FIELD_IDS")
    zendesk_nature_category_map: Dict[str, str] = Field(default_factory=dict, alias="ZENDESK_NATURE_CATEGORY_MAP")
    zendesk_nature_require_field: bool = Field(default=True, alias="ZENDESK_NATURE_REQUIRE_FIELD")
    # Debug: enable limited verification logs for Zendesk HMAC (do NOT enable in prod)
    zendesk_debug_verify: bool = Field(default=False, alias="ZENDESK_DEBUG_VERIFY")
    # Use HTML notes in Zendesk for better readability (fallback to text on failure)
    zendesk_use_html: bool = Field(default=True, alias="ZENDESK_USE_HTML")
    # Zendesk note formatting engine: legacy|markdown_v2
    zendesk_format_engine: str = Field(default="markdown_v2", alias="ZENDESK_FORMAT_ENGINE")
    # Formatting style for paragraph sentence breaks in HTML mode: compact|relaxed
    zendesk_format_style: str = Field(default="compact", alias="ZENDESK_FORMAT_STYLE")

    @field_validator("zendesk_format_engine")
    @classmethod
    def validate_zendesk_format_engine(cls, value: str) -> str:
        normalized = (value or "legacy").strip().lower()
        if normalized not in {"legacy", "markdown_v2"}:
            raise ValueError("zendesk_format_engine must be one of: legacy, markdown_v2")
        return normalized

    @field_validator("zendesk_clash_resolution")
    @classmethod
    def validate_zendesk_clash_resolution(cls, value: str) -> str:
        normalized = (value or "prefer_newer").strip().lower()
        if normalized not in {"prefer_newer"}:
            raise ValueError("zendesk_clash_resolution must be: prefer_newer")
        return normalized

    @field_validator("zendesk_drift_guard_strictness")
    @classmethod
    def validate_zendesk_drift_guard_strictness(cls, value: str) -> str:
        normalized = (value or "medium").strip().lower()
        if normalized not in {"low", "medium", "high"}:
            raise ValueError("zendesk_drift_guard_strictness must be low, medium, or high")
        return normalized

    @field_validator("zendesk_feedme_slice_window_before", "zendesk_feedme_slice_window_after")
    @classmethod
    def validate_zendesk_feedme_slice_windows(cls, value: int) -> int:
        value_int = int(value)
        if value_int < 0 or value_int > 10:
            raise ValueError("zendesk_feedme_slice_window must be between 0 and 10")
        return value_int

    @field_validator("zendesk_feedme_slice_max_chunks")
    @classmethod
    def validate_zendesk_feedme_slice_max_chunks(cls, value: int) -> int:
        value_int = int(value)
        if value_int < 1 or value_int > 50:
            raise ValueError("zendesk_feedme_slice_max_chunks must be between 1 and 50")
        return value_int

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

    @field_validator('zendesk_poll_interval_sec')
    @classmethod
    def validate_zendesk_poll_interval(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("zendesk_poll_interval_sec must be positive")
        return v

    @field_validator('zendesk_rpm_limit', 'zendesk_import_rpm_limit', 'zendesk_gemini_daily_limit', 'zendesk_max_retries')
    @classmethod
    def validate_zendesk_limits(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Zendesk limits must be positive integers")
        return v

    @field_validator('zendesk_monthly_api_budget')
    @classmethod
    def validate_zendesk_monthly_budget(cls, v: int) -> int:
        if v < 0:
            raise ValueError("zendesk_monthly_api_budget must be zero or a positive integer")
        return v

    @field_validator('zendesk_queue_retention_days')
    @classmethod
    def validate_zendesk_retention(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("zendesk_queue_retention_days must be positive")
        return v

    @field_validator(
        'zendesk_web_prefetch_pages',
        'zendesk_firecrawl_support_pages',
        'zendesk_internal_retrieval_max_per_source',
        'zendesk_issue_pattern_max_hits',
    )
    @classmethod
    def validate_zendesk_positive_ints(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("zendesk_* value must be positive")
        return v

    @field_validator(
        'zendesk_internal_retrieval_min_relevance',
        'zendesk_macro_min_relevance',
        'zendesk_feedme_min_relevance',
        'zendesk_issue_pattern_min_similarity',
    )
    @classmethod
    def validate_zendesk_relevance_thresholds(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("zendesk_* relevance threshold must be between 0.0 and 1.0")
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

    @field_validator('zendesk_windows_brand_ids', mode='before')
    @classmethod
    def parse_zendesk_windows_brand_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    return []
            return [item.strip() for item in raw.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @field_validator("zendesk_excluded_statuses", mode="before")
    @classmethod
    def parse_zendesk_excluded_statuses(cls, v):
        if v is None:
            return ["solved", "closed"]
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [
                            str(item).strip().lower()
                            for item in parsed
                            if str(item).strip()
                        ]
                except Exception:
                    return []
            return [item.strip().lower() for item in raw.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip().lower() for item in v if str(item).strip()]
        return []

    @field_validator("zendesk_excluded_tags", mode="before")
    @classmethod
    def parse_zendesk_excluded_tags(cls, v):
        if v is None:
            return ["mac_general__feature_delivered", "mb_spam_suspected"]
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [
                            str(item).strip().lower()
                            for item in parsed
                            if str(item).strip()
                        ]
                except Exception:
                    return []
            return [item.strip().lower() for item in raw.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip().lower() for item in v if str(item).strip()]
        return []

    @field_validator("zendesk_excluded_brand_ids", mode="before")
    @classmethod
    def parse_zendesk_excluded_brand_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    return []
            return [item.strip() for item in raw.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @field_validator('zendesk_nature_field_ids', mode='before')
    @classmethod
    def parse_zendesk_nature_field_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    return []
            return [item.strip() for item in raw.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @field_validator('zendesk_nature_category_map', mode='before')
    @classmethod
    def parse_zendesk_nature_category_map(cls, v):
        if v is None:
            return {}
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except Exception:
                return {}
            if isinstance(parsed, dict):
                return {
                    str(k).strip().lower(): str(val).strip().lower()
                    for k, val in parsed.items()
                    if str(k).strip() and str(val).strip()
                }
            return {}
        if isinstance(v, dict):
            return {
                str(k).strip().lower(): str(val).strip().lower()
                for k, val in v.items()
                if str(k).strip() and str(val).strip()
            }
        return {}

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
