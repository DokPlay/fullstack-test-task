from __future__ import annotations

import pytest

from src.core.database import create_database


@pytest.mark.asyncio
async def test_database_engine_uses_configured_pool_recycle() -> None:
    database = create_database(
        "sqlite+aiosqlite:///:memory:",
        pool_recycle_seconds=123,
    )

    try:
        assert database.engine.sync_engine.pool._recycle == 123
    finally:
        await database.aclose()


@pytest.mark.asyncio
async def test_postgresql_database_engine_uses_configured_pool_limits() -> None:
    database = create_database(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        pool_size=7,
        pool_max_overflow=3,
        pool_recycle_seconds=456,
    )

    try:
        pool = database.engine.sync_engine.pool
        assert pool.size() == 7
        assert pool._max_overflow == 3
        assert pool._recycle == 456
    finally:
        await database.aclose()
