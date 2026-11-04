import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from celery import Celery
from celery.signals import setup_logging as celery_setup_logging

from app.config import get_settings

T = TypeVar("T")

settings = get_settings()

celery_app = Celery(
    "domik",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.modules.notifications.tasks",
        "app.modules.bookings.tasks",
        "app.modules.excel_sync.tasks",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "send-due-reminders": {
            "task": "notifications.send_due_reminders",
            "schedule": 60.0,
        },
        "excel-sync": {
            "task": "excel_sync.sync_file",
            "schedule": float(settings.excel_sync_interval_seconds),
        },
    },
)


@celery_setup_logging.connect
def _configure_logging(**_: Any) -> None:
    from app.shared.logging import setup_logging

    setup_logging()


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Celery tasks are sync; each one runs its coroutine in a fresh event loop."""
    return asyncio.run(coro)


# `celery -A app.worker` looks for `app` / `celery` attributes
app = celery_app
