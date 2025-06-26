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

from app.core.settings import settings

logger = logging.getLogger(__name__)

# Create Celery application
celery_app = Celery(
    "feedme",
    broker=settings.feedme_celery_broker,
    backend=settings.feedme_result_backend,
    include=["app.feedme.tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Task routing
    task_routes={
        'app.feedme.tasks.process_transcript': {'queue': 'feedme_processing'},
        'app.feedme.tasks.generate_embeddings': {'queue': 'feedme_embeddings'},
        'app.feedme.tasks.parse_conversation': {'queue': 'feedme_parsing'},
        'app.feedme.tasks.health_check': {'queue': 'feedme_health'},
    },
    
    # Queue configuration
    task_default_queue='feedme_default',
    task_queues=(
        Queue('feedme_default', routing_key='feedme_default'),
        Queue('feedme_processing', routing_key='feedme_processing'),
        Queue('feedme_embeddings', routing_key='feedme_embeddings'),
        Queue('feedme_parsing', routing_key='feedme_parsing'),
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
    task_annotations={
        '*': {'rate_limit': '10/s'},
        'app.feedme.tasks.process_transcript': {
            'rate_limit': '5/m',  # 5 per minute for heavy processing
            'max_retries': 3,
            'default_retry_delay': 60,  # 1 minute
        },
        'app.feedme.tasks.generate_embeddings': {
            'rate_limit': '10/m',
            'max_retries': 2,
            'default_retry_delay': 30,
        },
        'app.feedme.tasks.parse_conversation': {
            'rate_limit': '20/m',
            'max_retries': 2,
            'default_retry_delay': 15,
        }
    }
)

# Task discovery
celery_app.autodiscover_tasks(['app.feedme'])


@worker_init.connect
def worker_init_handler(sender=None, **kwargs):
    """Initialize worker with necessary connections and configurations"""
    logger.info(f"Celery worker starting: {sender}")
    
    # Initialize database connections
    try:
        from app.db.connection_manager import get_connection_manager
        manager = get_connection_manager()
        stats = manager.get_stats()
        logger.info(f"Database connection pool initialized: {stats}")
    except Exception as e:
        logger.error(f"Failed to initialize database connections: {e}")
    
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
    
    try:
        from app.db.connection_manager import get_connection_manager
        manager = get_connection_manager()
        manager.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")


# Health check for Celery application
def check_celery_health():
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
            "broker": settings.feedme_celery_broker,
            "backend": settings.feedme_result_backend
        }
        
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    # Start worker for development
    logger.info("Starting Celery worker for FeedMe v2.0...")
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--queues=feedme_default,feedme_processing,feedme_embeddings,feedme_parsing,feedme_health"
    ])