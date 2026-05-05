from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, Protocol
from uuid import uuid4

from redis.asyncio import Redis

from src.core.settings import Settings
from src.models import Alert, StoredFile
from src.schemas import AlertItem, DashboardPatchEvent, DashboardSnapshotEvent, FileItem


DEFAULT_EVENT_NAME = "dashboard-update"
SNAPSHOT_EVENT_NAME = "dashboard-snapshot"
DEFAULT_SUBSCRIBER_QUEUE_SIZE = 256
DEFAULT_SUBSCRIBER_READY_TIMEOUT_SECONDS = 2.0
SSE_INITIAL_PADDING_BYTES = 2048
RedisFactory = Callable[[str], Redis]
BeforeSnapshotHook = Callable[[], Awaitable[None]]
logger = logging.getLogger(__name__)


class DashboardEventStream(Protocol):
    async def publish(self, event: DashboardPatchEvent) -> None: ...

    async def subscribe(
        self,
        *,
        snapshot_factory: Callable[[], Awaitable[DashboardSnapshotEvent]],
    ) -> AsyncIterator[str]: ...

    async def aclose(self) -> None: ...


def build_dashboard_snapshot(
    *,
    files: list[StoredFile],
    alerts: list[Alert],
) -> DashboardSnapshotEvent:
    return DashboardSnapshotEvent(
        occurred_at=_utcnow(),
        files=[_serialize_file(file_item) for file_item in files],
        alerts=[_serialize_alert(alert) for alert in alerts],
    )


def build_dashboard_patch(
    event_type: str,
    *,
    file: StoredFile | FileItem | None = None,
    alert: Alert | AlertItem | None = None,
    removed_file_id: str | None = None,
    removed_alerts_for_file_id: str | None = None,
) -> DashboardPatchEvent:
    return DashboardPatchEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        occurred_at=_utcnow(),
        file=_serialize_file(file),
        alert=_serialize_alert(alert),
        removed_file_id=removed_file_id,
        removed_alerts_for_file_id=removed_alerts_for_file_id,
    )


async def publish_dashboard_change_safely(
    publisher: Callable[[DashboardPatchEvent], Awaitable[None]] | None,
    event: DashboardPatchEvent,
    *,
    source_logger: logging.Logger,
) -> None:
    if publisher is None:
        return

    try:
        await publisher(event)
    except Exception:
        source_logger.exception("Failed to publish dashboard event %s", event.event_type)


class DashboardEventBus:
    def __init__(
        self,
        settings: Settings,
        redis_factory: RedisFactory | None = None,
        subscriber_ready_timeout_seconds: float = DEFAULT_SUBSCRIBER_READY_TIMEOUT_SECONDS,
    ):
        self.settings = settings
        self.channel_name = settings.dashboard_events_channel
        self.heartbeat_seconds = settings.dashboard_events_heartbeat_seconds
        self.retry_timeout_ms = settings.dashboard_events_retry_timeout_ms
        self.subscriber_queue_size = DEFAULT_SUBSCRIBER_QUEUE_SIZE
        self.subscriber_ready_timeout_seconds = subscriber_ready_timeout_seconds
        resolved_redis_factory = redis_factory or _create_redis_client
        self._publisher = resolved_redis_factory(settings.redis_url)
        self._subscriber = resolved_redis_factory(settings.redis_url)
        self._subscriber_bootstrap_task: asyncio.Task[None] | None = None
        self._subscriber_task: asyncio.Task[None] | None = None
        self._subscriber_start_lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._subscribers_lock = asyncio.Lock()

    async def publish(self, event: DashboardPatchEvent) -> None:
        payload = event.model_dump_json()
        await self._publisher.publish(self.channel_name, payload)

    async def aclose(self) -> None:
        if self._subscriber_bootstrap_task is not None:
            self._subscriber_bootstrap_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._subscriber_bootstrap_task
            self._subscriber_bootstrap_task = None

        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._subscriber_task
            self._subscriber_task = None

        async with self._subscribers_lock:
            self._subscribers.clear()

        await self._subscriber.aclose()
        await self._publisher.aclose()

    async def subscribe(
        self,
        *,
        snapshot_factory: Callable[[], Awaitable[DashboardSnapshotEvent]],
    ) -> AsyncIterator[str]:
        yield _format_retry(self.retry_timeout_ms)

        subscriber: asyncio.Queue[str] = asyncio.Queue(maxsize=self.subscriber_queue_size)

        async with self._subscribers_lock:
            self._subscribers.add(subscriber)

        try:
            self._start_subscriber_task_without_blocking_snapshot()
            await self._wait_for_subscriber_bootstrap()
            snapshot = await snapshot_factory()
            yield _format_event(SNAPSHOT_EVENT_NAME, snapshot.model_dump_json())

            async for chunk in _stream_patches(
                subscriber=subscriber,
                heartbeat_seconds=self.heartbeat_seconds,
            ):
                yield chunk
        finally:
            async with self._subscribers_lock:
                self._subscribers.discard(subscriber)

    def _start_subscriber_task_without_blocking_snapshot(self) -> None:
        if (
            self._subscriber_bootstrap_task is not None
            and not self._subscriber_bootstrap_task.done()
        ):
            return

        self._subscriber_bootstrap_task = asyncio.create_task(
            self._ensure_subscriber_task_with_timeout(),
        )

    async def _wait_for_subscriber_bootstrap(self) -> None:
        if self._subscriber_bootstrap_task is None:
            return

        await self._subscriber_bootstrap_task

    async def _ensure_subscriber_task_with_timeout(self) -> None:
        try:
            await asyncio.wait_for(
                self._ensure_subscriber_task(),
                timeout=self.subscriber_ready_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "Dashboard Redis subscriber did not become ready within %.1f seconds; "
                "streaming the initial snapshot without blocking the SSE response",
                self.subscriber_ready_timeout_seconds,
            )
        except Exception:
            logger.exception(
                "Dashboard Redis subscriber failed to start; streaming the initial snapshot anyway",
            )

    async def _ensure_subscriber_task(self) -> None:
        async with self._subscriber_start_lock:
            if self._subscriber_task is not None and not self._subscriber_task.done():
                return

            ready = asyncio.Event()
            self._subscriber_task = asyncio.create_task(self._consume_redis_events(ready))
            await ready.wait()

            if self._subscriber_task.done():
                self._subscriber_task.result()

    async def _consume_redis_events(self, ready: asyncio.Event) -> None:
        pubsub = self._subscriber.pubsub()

        try:
            await pubsub.subscribe(self.channel_name)
            ready.set()

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=self.heartbeat_seconds,
                )
                if message is None:
                    continue

                data = message.get("data")
                if isinstance(data, str):
                    await self._publish_to_local_subscribers(data)
        finally:
            ready.set()
            with suppress(Exception):
                await pubsub.unsubscribe(self.channel_name)
            with suppress(Exception):
                await pubsub.aclose()

    async def _publish_to_local_subscribers(self, payload: str) -> None:
        async with self._subscribers_lock:
            subscribers = tuple(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropped dashboard event because a Redis subscriber queue is full",
                )


class InMemoryDashboardEventBus:
    def __init__(
        self,
        *,
        heartbeat_seconds: int = 15,
        retry_timeout_ms: int = 3000,
        subscriber_queue_size: int = DEFAULT_SUBSCRIBER_QUEUE_SIZE,
    ):
        self.heartbeat_seconds = heartbeat_seconds
        self.retry_timeout_ms = retry_timeout_ms
        self.subscriber_queue_size = subscriber_queue_size
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._subscribers_lock = asyncio.Lock()

    async def publish(self, event: DashboardPatchEvent) -> None:
        payload = event.model_dump_json()
        async with self._subscribers_lock:
            for subscriber in list(self._subscribers):
                try:
                    subscriber.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.warning(
                        "Dropped dashboard event %s because an in-memory subscriber queue is full",
                        event.event_type,
                    )

    async def aclose(self) -> None:
        async with self._subscribers_lock:
            self._subscribers.clear()

    async def subscribe(
        self,
        *,
        snapshot_factory: Callable[[], Awaitable[DashboardSnapshotEvent]],
    ) -> AsyncIterator[str]:
        subscriber: asyncio.Queue[str] = asyncio.Queue(maxsize=self.subscriber_queue_size)

        async with self._subscribers_lock:
            self._subscribers.add(subscriber)

        try:
            async for chunk in _stream_snapshot_then_patches(
                subscriber=subscriber,
                snapshot_factory=snapshot_factory,
                heartbeat_seconds=self.heartbeat_seconds,
                retry_timeout_ms=self.retry_timeout_ms,
            ):
                yield chunk
        finally:
            async with self._subscribers_lock:
                self._subscribers.discard(subscriber)


async def _stream_snapshot_then_patches(
    *,
    subscriber: asyncio.Queue[str],
    snapshot_factory: Callable[[], Awaitable[DashboardSnapshotEvent]],
    before_snapshot: BeforeSnapshotHook | None = None,
    heartbeat_seconds: int,
    retry_timeout_ms: int,
) -> AsyncIterator[str]:
    yield _format_retry(retry_timeout_ms)

    if before_snapshot is not None:
        await before_snapshot()

    snapshot = await snapshot_factory()
    yield _format_event(SNAPSHOT_EVENT_NAME, snapshot.model_dump_json())

    async for chunk in _stream_patches(
        subscriber=subscriber,
        heartbeat_seconds=heartbeat_seconds,
    ):
        yield chunk


async def _stream_patches(
    *,
    subscriber: asyncio.Queue[str],
    heartbeat_seconds: int,
) -> AsyncIterator[str]:
    while True:
        while True:
            try:
                payload = subscriber.get_nowait()
            except asyncio.QueueEmpty:
                break

            yield _format_event(DEFAULT_EVENT_NAME, payload)

        try:
            payload = await asyncio.wait_for(
                subscriber.get(),
                timeout=heartbeat_seconds,
            )
        except TimeoutError:
            yield ": keepalive\n\n"
            continue

        yield _format_event(DEFAULT_EVENT_NAME, payload)


def _format_retry(retry_timeout_ms: int) -> str:
    # Some dev proxies and Docker Desktop port forwarding paths buffer tiny
    # streaming responses. SSE comments are ignored by EventSource but force an
    # early flush before the initial dashboard snapshot.
    return f": {' ' * SSE_INITIAL_PADDING_BYTES}\nretry: {retry_timeout_ms}\n\n"


def _create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


def _format_event(event_name: str, payload: str) -> str:
    return f"event: {event_name}\ndata: {payload}\n\n"


def _serialize_file(file_item: StoredFile | FileItem | None) -> FileItem | None:
    if file_item is None:
        return None
    if isinstance(file_item, FileItem):
        return file_item
    return FileItem.model_validate(file_item)


def _serialize_alert(alert: Alert | AlertItem | None) -> AlertItem | None:
    if alert is None:
        return None
    if isinstance(alert, AlertItem):
        return alert
    return AlertItem.model_validate(alert)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
