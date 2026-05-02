from __future__ import annotations

from typing import Protocol

from celery import Celery


PROCESS_FILE_TASK_NAME = "src.tasks.process_file"


class FileProcessingQueue(Protocol):
    def enqueue_file_processing(self, file_id: str) -> None: ...


class CeleryFileProcessingQueue:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._celery_app: Celery | None = None

    def enqueue_file_processing(self, file_id: str) -> None:
        self._get_celery_app().send_task(PROCESS_FILE_TASK_NAME, args=(file_id,))

    def _get_celery_app(self) -> Celery:
        if self._celery_app is None:
            self._celery_app = Celery("file_tasks_client", broker=self.redis_url, backend=self.redis_url)
        return self._celery_app
