"""Celery worker configuration and beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings
from app.logging import configure_logging

# Configure logging
configure_logging()

# Create Celery app
app = Celery(
    "football_ingest",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.ingest.tasks"],
)

# Celery configuration
app.conf.update(
    # Timezone configuration
    timezone=settings.TIMEZONE,
    enable_utc=True,
    
    # Task configuration
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    
    # Beat schedule
    beat_schedule={
        "daily_llm_data_sync": {
            "task": "ingest.daily_llm_data_sync",
            "schedule": crontab(minute=0, hour=2),  # 02:00 UTC daily
            "options": {"queue": "default"},
        },
        "sync_upcoming_fixtures_6h": {
            "task": "ingest.sync_upcoming_fixtures",
            "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
            "args": (settings.FIXTURE_HORIZON_DAYS,),
            "options": {"queue": "default"},
        },
        "sync_finished_fixtures_daily": {
            "task": "ingest.sync_finished_fixtures",
            "schedule": crontab(minute=30, hour=3),  # 03:30 UTC daily
            "args": (30,),  # Last 30 days
            "options": {"queue": "default"},
        },
    },
    
    # Queue routing
    task_routes={
        "ingest.*": {"queue": "default"},
    },
)


# Error handling
@app.task(bind=True)
def debug_task(self) -> str:
    """Debug task for testing Celery configuration."""
    return f"Request: {self.request!r}"


# Task failure handler
@app.task(bind=True)
def handle_task_failure(self, task_id: str, error: str, traceback: str) -> None:
    """Handle task failures."""
    from app.logging import get_logger
    
    logger = get_logger("celery")
    logger.error(f"Task {task_id} failed: {error}")
    logger.error(f"Traceback: {traceback}")


# Connect failure signal
from celery.signals import task_failure

@task_failure.connect
def handle_failure(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwargs):
    """Handle task failures globally."""
    from app.logging import get_logger
    
    logger = get_logger("celery")
    logger.error(f"Task {task_id} failed with exception: {exception}")
    if traceback:
        logger.error(f"Traceback: {traceback}")


# Health check task
@app.task
def health_check() -> Dict[str, str]:
    """Health check task."""
    import pendulum
    from typing import Dict
    
    return {
        "status": "healthy",
        "timestamp": pendulum.now().to_iso8601_string(),
        "worker": "football_ingest",
    }


if __name__ == "__main__":
    app.start()