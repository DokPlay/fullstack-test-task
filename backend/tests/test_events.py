from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.schemas import DashboardSnapshotEvent
from src.services.events import DashboardEventBus, InMemoryDashboardEventBus, build_dashboard_patch
from tests.conftest import build_test_settings


class FakeRedisBroker:
    def __init__(self) -> None:
        self.pubsub_count = 0
        self.pubsubs: list[FakePubSub] = []

    def create_pubsub(self) -> FakePubSub:
        pubsub = FakePubSub()
        self.pubsub_count += 1
        self.pubsubs.append(pubsub)
        return pubsub

    async def publish(self, payload: str) -> None:
        for pubsub in self.pubsubs:
            if pubsub.subscribed:
                pubsub.messages.put_nowait({"data": payload})


class FakePubSub:
    def __init__(self) -> None:
        self.messages: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        self.subscribed = False

    async def subscribe(self, _channel_name: str) -> None:
        self.subscribed = True

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: int,
    ) -> dict[str, str] | None:
        try:
            return await asyncio.wait_for(self.messages.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def unsubscribe(self, _channel_name: str) -> None:
        self.subscribed = False

    async def aclose(self) -> None:
        self.subscribed = False


class HangingSubscribePubSub(FakePubSub):
    async def subscribe(self, _channel_name: str) -> None:
        await asyncio.Event().wait()


class HangingSubscribeBroker(FakeRedisBroker):
    def create_pubsub(self) -> FakePubSub:
        pubsub = HangingSubscribePubSub()
        self.pubsub_count += 1
        self.pubsubs.append(pubsub)
        return pubsub


class FakeRedis:
    def __init__(self, broker: FakeRedisBroker) -> None:
        self.broker = broker
        self.closed = False

    def pubsub(self) -> FakePubSub:
        return self.broker.create_pubsub()

    async def publish(self, _channel_name: str, payload: str) -> None:
        await self.broker.publish(payload)

    async def aclose(self) -> None:
        self.closed = True


def assert_retry_chunk(chunk: str, retry_timeout_ms: int) -> None:
    assert chunk.startswith(": ")
    assert chunk.endswith(f"retry: {retry_timeout_ms}\n\n")


@pytest.mark.asyncio
async def test_dashboard_event_bus_fans_out_with_one_redis_pubsub(tmp_path: Path) -> None:
    broker = FakeRedisBroker()
    clients: list[FakeRedis] = []

    def redis_factory(_redis_url: str) -> FakeRedis:
        client = FakeRedis(broker)
        clients.append(client)
        return client

    settings = build_test_settings(tmp_path / "storage")
    event_bus = DashboardEventBus(settings, redis_factory=redis_factory)

    async def snapshot_factory() -> DashboardSnapshotEvent:
        return DashboardSnapshotEvent(
            occurred_at=datetime.now(timezone.utc),
            files=[],
            alerts=[],
        )

    first_stream = event_bus.subscribe(snapshot_factory=snapshot_factory)
    second_stream = event_bus.subscribe(snapshot_factory=snapshot_factory)

    try:
        assert_retry_chunk(await anext(first_stream), settings.dashboard_events_retry_timeout_ms)
        first_snapshot = await anext(first_stream)
        assert first_snapshot.startswith("event: dashboard-snapshot\ndata: {\"kind\":\"snapshot\"")

        assert_retry_chunk(await anext(second_stream), settings.dashboard_events_retry_timeout_ms)
        second_snapshot = await anext(second_stream)
        assert second_snapshot.startswith("event: dashboard-snapshot\ndata: {\"kind\":\"snapshot\"")

        await event_bus.publish(build_dashboard_patch("fanout.test"))

        first_update = await asyncio.wait_for(anext(first_stream), timeout=1)
        second_update = await asyncio.wait_for(anext(second_stream), timeout=1)

        assert first_update.startswith("event: dashboard-update\ndata: ")
        assert second_update.startswith("event: dashboard-update\ndata: ")
        assert "\"event_type\":\"fanout.test\"" in first_update
        assert "\"event_type\":\"fanout.test\"" in second_update
        assert broker.pubsub_count == 1
        assert len(clients) == 2

    finally:
        await first_stream.aclose()
        await second_stream.aclose()
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_dashboard_event_bus_does_not_block_snapshot_when_redis_subscribe_hangs(
    tmp_path: Path,
) -> None:
    broker = HangingSubscribeBroker()

    def redis_factory(_redis_url: str) -> FakeRedis:
        return FakeRedis(broker)

    settings = build_test_settings(tmp_path / "storage")
    event_bus = DashboardEventBus(
        settings,
        redis_factory=redis_factory,
        subscriber_ready_timeout_seconds=0.01,
    )

    async def snapshot_factory() -> DashboardSnapshotEvent:
        return DashboardSnapshotEvent(
            occurred_at=datetime.now(timezone.utc),
            files=[],
            alerts=[],
        )

    stream = event_bus.subscribe(snapshot_factory=snapshot_factory)

    try:
        retry_chunk = await asyncio.wait_for(anext(stream), timeout=1)
        snapshot_chunk = await asyncio.wait_for(anext(stream), timeout=1)

        assert_retry_chunk(retry_chunk, settings.dashboard_events_retry_timeout_ms)
        assert snapshot_chunk.startswith("event: dashboard-snapshot\ndata: ")
    finally:
        await stream.aclose()
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_dashboard_event_bus_sends_snapshot_before_buffered_patches(tmp_path: Path) -> None:
    broker = FakeRedisBroker()

    def redis_factory(_redis_url: str) -> FakeRedis:
        return FakeRedis(broker)

    settings = build_test_settings(tmp_path / "storage")
    event_bus = DashboardEventBus(settings, redis_factory=redis_factory)

    async def snapshot_factory() -> DashboardSnapshotEvent:
        await event_bus.publish(build_dashboard_patch("snapshot.window"))
        await asyncio.sleep(0)
        return DashboardSnapshotEvent(
            occurred_at=datetime.now(timezone.utc),
            files=[],
            alerts=[],
        )

    stream = event_bus.subscribe(snapshot_factory=snapshot_factory)

    try:
        assert_retry_chunk(await anext(stream), settings.dashboard_events_retry_timeout_ms)

        snapshot_chunk = await asyncio.wait_for(anext(stream), timeout=1)
        patch_chunk = await asyncio.wait_for(anext(stream), timeout=1)

        assert snapshot_chunk.startswith("event: dashboard-snapshot\ndata: ")
        assert patch_chunk.startswith("event: dashboard-update\ndata: ")
        assert "\"event_type\":\"snapshot.window\"" in patch_chunk

    finally:
        await stream.aclose()
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_in_memory_dashboard_event_bus_drops_events_when_subscriber_queue_is_full() -> None:
    event_bus = InMemoryDashboardEventBus(
        heartbeat_seconds=10,
        retry_timeout_ms=3000,
        subscriber_queue_size=1,
    )

    async def snapshot_factory() -> DashboardSnapshotEvent:
        return DashboardSnapshotEvent(
            occurred_at=datetime.now(timezone.utc),
            files=[],
            alerts=[],
        )

    stream = event_bus.subscribe(snapshot_factory=snapshot_factory)

    try:
        assert_retry_chunk(await anext(stream), 3000)
        assert (await anext(stream)).startswith("event: dashboard-snapshot\ndata: ")

        await event_bus.publish(build_dashboard_patch("queued.first"))
        await event_bus.publish(build_dashboard_patch("queued.second"))

        update_chunk = await asyncio.wait_for(anext(stream), timeout=1)
        assert "\"event_type\":\"queued.first\"" in update_chunk

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(anext(stream), timeout=0.05)
    finally:
        await stream.aclose()
        await event_bus.aclose()
