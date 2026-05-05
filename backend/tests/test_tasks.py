from __future__ import annotations

from src.tasks import _run_task_with_metrics


def test_task_metrics_wrapper_returns_coroutine_result() -> None:
    async def recover_ids() -> list[str]:
        return ["file-a", "file-b"]

    assert _run_task_with_metrics("tests.recover_ids", recover_ids()) == ["file-a", "file-b"]
