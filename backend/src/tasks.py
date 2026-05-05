from __future__ import annotations

import asyncio
import logging
import os

from celery import Celery
from prometheus_client import Counter, Gauge, start_http_server

from src.core.container import ApplicationContainer, create_container
from src.core.settings import get_settings
from src.services.processing import FileProcessingService

logger = logging.getLogger(__name__)

settings = get_settings()
_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_container: ApplicationContainer | None = None
_metrics_started = False

WORKER_METRICS_ENABLED = os.getenv("WORKER_METRICS_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WORKER_METRICS_PORT = 0
WORKER_TASKS_IN_PROGRESS = Gauge(
    "celery_worker_tasks_in_progress",
    "Number of worker tasks currently being executed.",
    ["task_name"],
)
WORKER_TASKS_STARTED = Counter(
    "celery_worker_tasks_started_total",
    "Number of started worker tasks.",
    ["task_name"],
)
WORKER_TASKS_COMPLETED = Counter(
    "celery_worker_tasks_completed_total",
    "Number of completed worker tasks by status.",
    ["task_name", "status"],
)


def _parse_worker_metrics_port() -> int:
    raw_port = os.getenv("WORKER_METRICS_PORT", "0")
    try:
        port = int(raw_port)
    except ValueError:
        logger.warning("Invalid WORKER_METRICS_PORT value %r, metrics server disabled", raw_port)
        return 0

    if port < 0 or port > 65535:
        logger.warning("WORKER_METRICS_PORT %s is outside TCP port range, metrics server disabled", port)
        return 0

    return port


def _start_metrics_server() -> None:
    global _metrics_started
    if not WORKER_METRICS_ENABLED or _metrics_started or WORKER_METRICS_PORT <= 0:
        return

    try:
        start_http_server(WORKER_METRICS_PORT)
        _metrics_started = True
    except Exception:
        logger.exception(
            "Failed to start worker metrics server on port %s",
            WORKER_METRICS_PORT,
        )


def _run_task_with_metrics(task_name: str, coroutine):
    WORKER_TASKS_STARTED.labels(task_name=task_name).inc()
    WORKER_TASKS_IN_PROGRESS.labels(task_name=task_name).inc()
    try:
        result = run_in_worker_loop(coroutine)
        WORKER_TASKS_COMPLETED.labels(task_name=task_name, status="success").inc()
        return result
    except Exception:
        WORKER_TASKS_COMPLETED.labels(task_name=task_name, status="failed").inc()
        raise
    finally:
        WORKER_TASKS_IN_PROGRESS.labels(task_name=task_name).dec()


def run_in_worker_loop(coroutine):
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coroutine)


def _build_celery_app() -> Celery:
    return Celery("file_tasks", broker=settings.redis_url, backend=settings.redis_url)


WORKER_METRICS_PORT = _parse_worker_metrics_port()
_start_metrics_server()

celery_app = _build_celery_app()
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "recover-stuck-files": {
            "task": "src.tasks.recover_stuck_files",
            "schedule": settings.processing_recovery_interval_seconds,
        }
    },
    timezone="UTC",
)


def get_worker_container() -> ApplicationContainer:
    global _worker_container
    if _worker_container is None:
        _worker_container = create_container(settings=settings)
    return _worker_container


def get_processing_service() -> FileProcessingService:
    return get_worker_container().processing_service


@celery_app.task(name="src.tasks.process_file")
def process_file(file_id: str) -> None:
    _run_task_with_metrics("src.tasks.process_file", get_processing_service().process_file(file_id))


@celery_app.task(name="src.tasks.recover_stuck_files")
def recover_stuck_files() -> int:
    recovered_file_ids = _run_task_with_metrics(
        "src.tasks.recover_stuck_files",
        get_processing_service().recover_stuck_files(),
    )
    for file_id in recovered_file_ids:
        process_file.delay(file_id)
    return len(recovered_file_ids)
