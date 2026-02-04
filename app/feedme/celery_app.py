"""
FeedMe v2.0 Phase 2: Celery Application Configuration
Async processing pipeline for transcript parsing and embedding generation

This module provides:
- Celery application setup with Redis broker
- Task routing and configuration
- Error handling and retry policies
- Monitoring and health checks
"""

import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
from threading import Thread
from typing import Dict, Any, Type

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import worker_init, worker_shutdown  # type: ignore[import-untyped]
from celery import Task  # type: ignore[import-untyped]
from kombu import Queue  # type: ignore[import-untyped]
import psycopg2  # type: ignore[import-untyped]
import requests

from app.core.settings import settings

logger = logging.getLogger(__name__)
_health_server: HTTPServer | None = None

# Create Celery application
# Set default broker/backend if not configured
default_broker = "redis://localhost:6379/1"
default_backend = "redis://localhost:6379/2"


def _optional_int_env(name: str, default: int | None) -> int | None:
    """Parse an optional int env var; <=0 disables the limit (None)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value <= 0:
        return None
    return value

celery_app = Celery(
    "feedme",
    broker=getattr(settings, "feedme_celery_broker", default_broker),
    backend=getattr(settings, "feedme_result_backend", default_backend),
    include=["app.feedme.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Broker resilience (Railway Redis can reset idle connections)
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    # None = retry forever
    broker_connection_max_retries=None,
    broker_transport_options={
        # With acks_late enabled, tasks must remain invisible while executing.
        # Keep comfortably above any configured task_time_limit.
        "visibility_timeout": int(
            os.getenv("FEEDME_CELERY_VISIBILITY_TIMEOUT", "3600")
        ),
        # Keep connections alive and proactively detect dead sockets.
        "health_check_interval": int(
            os.getenv("FEEDME_CELERY_HEALTH_CHECK_INTERVAL", "30")
        ),
        "retry_on_timeout": True,
        "socket_timeout": int(os.getenv("FEEDME_CELERY_SOCKET_TIMEOUT", "30")),
        "socket_connect_timeout": int(
            os.getenv("FEEDME_CELERY_SOCKET_CONNECT_TIMEOUT", "30")
        ),
        "socket_keepalive": True,
    },
    # Task routing
    task_routes={
        "app.feedme.tasks.process_transcript": {"queue": "feedme_processing"},
        "app.feedme.tasks.generate_text_chunks_and_embeddings": {
            "queue": "feedme_embeddings"
        },
        "app.feedme.tasks.generate_ai_tags": {"queue": "feedme_processing"},
        "app.feedme.tasks.import_zendesk_tagged": {"queue": "feedme_processing"},
        "app.feedme.tasks.health_check": {"queue": "feedme_health"},
    },
    # Queue configuration
    task_default_queue="feedme_default",
    task_queues=(
        Queue("feedme_default", routing_key="feedme_default"),
        Queue("feedme_processing", routing_key="feedme_processing"),
        Queue("feedme_embeddings", routing_key="feedme_embeddings"),
        # 'feedme_parsing' queue removed with deprecation of parse_conversation
        Queue("feedme_health", routing_key="feedme_health"),
    ),
    # Task execution
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task result settings
    result_expires=3600,  # 1 hour
    result_persistent=True,
    # Task retry configuration
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Task time limits
    task_soft_time_limit=_optional_int_env(
        "FEEDME_CELERY_SOFT_TIME_LIMIT", None
    ),
    task_time_limit=_optional_int_env("FEEDME_CELERY_TIME_LIMIT", None),
    # Worker configuration - Memory optimization
    # Restart worker after 50 tasks to prevent memory accumulation from PDF processing
    worker_max_tasks_per_child=50,
    # Restart worker if memory exceeds 512MB (in KB) - Celery 5.2+ feature
    worker_max_memory_per_child=512000,
    worker_disable_rate_limits=True,
    # Monitoring
    task_send_sent_event=True,
    task_track_started=True,
    worker_send_task_events=True,
    # Error handling
    # Default task retry policy for unexpected errors
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 10,  # seconds
        "interval_step": 10,
        "interval_max": 60,
    },
)

# Task discovery
celery_app.autodiscover_tasks(["app.feedme"])


# --- Type-Safe Base Task with Retry --- #

RETRYABLE_EXCEPTIONS: tuple[Type[Exception], ...] = (
    psycopg2.OperationalError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class BaseTaskWithRetry(Task):
    """
    A base Celery task with built-in, type-safe retry logic for recoverable errors.

    Handles common transient issues like DB connection errors or network timeouts
    with exponential backoff.
    """

    autoretry_for = RETRYABLE_EXCEPTIONS
    retry_kwargs = {"max_retries": 3}
    retry_backoff = True
    retry_backoff_max = 60  # Max delay 60 seconds
    task_acks_late = True

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log when a task is being retried."""
        logging.warning(
            f"Task {task_id} retrying (attempt {self.request.retries + 1}/{self.max_retries}) "
            f"due to {type(exc).__name__}: {exc}"
        )
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log on final task failure after all retries are exhausted."""
        logging.error(
            f"Task {task_id} failed permanently after {self.request.retries} retries "
            f"due to {type(exc).__name__}: {exc}"
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)


@worker_init.connect
def worker_init_handler(sender=None, **kwargs):
    """Initialize worker with necessary connections and configurations"""
    logger.info(f"Celery worker starting: {sender}")

    _start_worker_health_server()

    # Initialize Supabase client
    try:
        from app.db.supabase.client import get_supabase_client

        get_supabase_client()
        logger.info("Supabase client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")

    # Initialize embedding model
    try:
        from app.db.embedding.utils import get_embedding_model

        get_embedding_model()
        logger.info("Embedding model initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {e}")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Clean up worker resources on shutdown to prevent memory leaks."""
    logger.info(f"Celery worker shutting down: {sender}")

    # Clear Gemini client singleton from tasks.py
    try:
        from app.feedme import tasks

        if hasattr(tasks, "_genai_client") and tasks._genai_client is not None:
            tasks._genai_client = None
            logger.info("Cleared tasks Gemini client")
    except Exception as e:
        logger.warning(f"Failed to clear tasks Gemini client: {e}")

    # Clear Gemini client singleton from gemini_pdf_processor
    try:
        from app.feedme.processors import gemini_pdf_processor

        if (
            hasattr(gemini_pdf_processor, "_genai_client")
            and gemini_pdf_processor._genai_client is not None
        ):
            gemini_pdf_processor._genai_client = None
            gemini_pdf_processor._genai_client_api_key = None
            logger.info("Cleared PDF processor Gemini client")
    except Exception as e:
        logger.warning(f"Failed to clear PDF processor Gemini client: {e}")

    # Clear embedding model LRU cache
    try:
        from app.db.embedding.utils import get_embedding_model

        get_embedding_model.cache_clear()
        logger.info("Cleared embedding model cache")
    except Exception as e:
        logger.warning(f"Failed to clear embedding model cache: {e}")

    # Clear rate tracker singletons
    try:
        from app.feedme.rate_limiting import gemini_tracker

        gemini_tracker._tracker = None
        gemini_tracker._embed_tracker = None
        logger.info("Cleared rate tracker singletons")
    except Exception as e:
        logger.warning(f"Failed to clear rate trackers: {e}")

    # Force garbage collection to release memory
    import gc

    gc.collect()
    logger.info("Worker shutdown complete with memory cleanup")


# Health check for Celery application
def check_celery_health() -> Dict[str, Any]:
    """Check Celery application health"""
    try:
        # Check if Celery is responsive
        inspect = celery_app.control.inspect()
        stats = inspect.stats()

        if not stats:
            return {"status": "unhealthy", "error": "No workers available"}

        # Check active tasks
        active_tasks = inspect.active()
        reserved_tasks = inspect.reserved()

        total_workers = len(stats) if stats else 0
        total_active = (
            sum(len(tasks) for tasks in active_tasks.values()) if active_tasks else 0
        )
        total_reserved = (
            sum(len(tasks) for tasks in reserved_tasks.values())
            if reserved_tasks
            else 0
        )

        return {
            "status": "healthy",
            "workers": total_workers,
            "active_tasks": total_active,
            "reserved_tasks": total_reserved,
            "queues": list(celery_app.conf.task_queues),
            "broker": getattr(settings, "feedme_celery_broker", default_broker),
            "backend": getattr(settings, "feedme_result_backend", default_backend),
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": {"type": type(e).__name__, "message": str(e)},
        }


def _start_worker_health_server() -> None:
    """Start a lightweight HTTP health endpoint for Railway worker checks."""
    global _health_server
    if _health_server is not None:
        return

    health_port_raw = os.getenv("HEALTH_PORT")
    port_raw = health_port_raw or os.getenv("PORT") or "8000"
    try:
        port = int(port_raw)
    except ValueError:
        logger.warning("Invalid health port %r; defaulting to 8000", port_raw)
        port = 8000

    if health_port_raw is None:
        # When running locally (backend + worker in the same environment), the worker
        # health server must not bind to the backend port. Some macOS combinations
        # allow multiple listeners on the same port, causing intermittent 404s.
        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                in_use = sock.connect_ex(("127.0.0.1", port)) == 0
        except Exception:
            in_use = False

        if in_use:
            fallback = port + 1
            logger.info(
                "Health port %s already in use; falling back to %s", port, fallback
            )
            port = fallback

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_args) -> None:
            # Silence default request logs in worker containers.
            return

    try:
        _health_server = HTTPServer(("", port), HealthHandler)
    except OSError as exc:
        logger.warning("Health server failed to bind on port %s: %s", port, exc)
        _health_server = None
        return

    thread = Thread(target=_health_server.serve_forever, daemon=True)
    thread.start()
    logger.info("Worker health server listening on port %s", port)


if __name__ == "__main__":
    # Start worker for development
    logger.info("Starting Celery worker for FeedMe v2.0...")
    celery_app.worker_main(
        [
            "worker",
            "--loglevel=info",
            "--concurrency=2",
            "--queues=feedme_default,feedme_processing,feedme_embeddings,feedme_health",
        ]
    )
