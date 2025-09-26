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
from celery import Celery
from celery.signals import worker_init, worker_shutdown
from kombu import Queue
import logging
from typing import Dict, Any, Type
from celery import Task
import psycopg2
import requests

from app.core.settings import settings

logger = logging.getLogger(__name__)

# Create Celery application
# Set default broker/backend if not configured
default_broker = "redis://localhost:6379/1"
default_backend = "redis://localhost:6379/2"

celery_app = Celery(
    "feedme",
    broker=getattr(settings, 'feedme_celery_broker', default_broker),
    backend=getattr(settings, 'feedme_result_backend', default_backend),
    include=["app.feedme.tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Task routing
    task_routes={
        'app.feedme.tasks.process_transcript': {'queue': 'feedme_processing'},
        'app.feedme.tasks.generate_text_chunks_and_embeddings': {'queue': 'feedme_embeddings'},
        'app.feedme.tasks.generate_ai_tags': {'queue': 'feedme_processing'},
        'app.feedme.tasks.health_check': {'queue': 'feedme_health'},
    },
    
    # Queue configuration
    task_default_queue='feedme_default',
    task_queues=(
        Queue('feedme_default', routing_key='feedme_default'),
        Queue('feedme_processing', routing_key='feedme_processing'),
        Queue('feedme_embeddings', routing_key='feedme_embeddings'),
        # 'feedme_parsing' queue removed with deprecation of parse_conversation
        Queue('feedme_health', routing_key='feedme_health'),
    ),
    
    # Task execution
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task result settings
    result_expires=3600,  # 1 hour
    result_persistent=True,
    
    # Task retry configuration
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    
    # Task time limits
    task_soft_time_limit=300,  # 5 minutes
    task_time_limit=600,       # 10 minutes
    
    # Worker configuration
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=True,
    
    # Monitoring
    task_send_sent_event=True,
    task_track_started=True,
    worker_send_task_events=True,
    
    # Error handling
    # Default task retry policy for unexpected errors
    task_publish_retry_policy = {
        'max_retries': 3,
        'interval_start': 10,  # seconds
        'interval_step': 10,
        'interval_max': 60,
    }
)

# Task discovery
celery_app.autodiscover_tasks(['app.feedme'])


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
    retry_kwargs = {'max_retries': 3}
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
    
    # Initialize Supabase client
    try:
        from app.db.supabase_client import get_supabase_client
        client = get_supabase_client()
        logger.info("Supabase client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
    
    # Initialize embedding model
    try:
        from app.db.embedding_utils import get_embedding_model
        model = get_embedding_model()
        logger.info("Embedding model initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {e}")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Clean up worker resources on shutdown"""
    logger.info(f"Celery worker shutting down: {sender}")
    
    # Supabase client cleanup handled automatically
    logger.info("Worker shutdown complete")


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
        total_active = sum(len(tasks) for tasks in active_tasks.values()) if active_tasks else 0
        total_reserved = sum(len(tasks) for tasks in reserved_tasks.values()) if reserved_tasks else 0
        
        return {
            "status": "healthy",
            "workers": total_workers,
            "active_tasks": total_active,
            "reserved_tasks": total_reserved,
            "queues": list(celery_app.conf.task_queues),
            "broker": getattr(settings, 'feedme_celery_broker', default_broker),
            "backend": getattr(settings, 'feedme_result_backend', default_backend)
        }
        
    except Exception as e:
        return {
            "status": "unhealthy", 
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            }
        }


if __name__ == "__main__":
    # Start worker for development
    logger.info("Starting Celery worker for FeedMe v2.0...")
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--queues=feedme_default,feedme_processing,feedme_embeddings,feedme_health"
    ])
