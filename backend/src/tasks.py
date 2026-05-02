from __future__ import annotations

import asyncio

from celery import Celery

from src.core.container import ApplicationContainer, create_container
from src.core.settings import get_settings
from src.services.processing import FileProcessingService

settings = get_settings()
_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_container: ApplicationContainer | None = None


def run_in_worker_loop(coroutine):
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coroutine)


celery_app = Celery("file_tasks", broker=settings.redis_url, backend=settings.redis_url)
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
    run_in_worker_loop(get_processing_service().process_file(file_id))


@celery_app.task(name="src.tasks.recover_stuck_files")
def recover_stuck_files() -> int:
    recovered_file_ids = run_in_worker_loop(get_processing_service().recover_stuck_files())
    for file_id in recovered_file_ids:
        process_file.delay(file_id)
    return len(recovered_file_ids)
