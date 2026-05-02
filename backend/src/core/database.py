from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.core.settings import (
    DEFAULT_DATABASE_POOL_MAX_OVERFLOW,
    DEFAULT_DATABASE_POOL_RECYCLE_SECONDS,
    DEFAULT_DATABASE_POOL_SIZE,
)


@dataclass(frozen=True, slots=True)
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def aclose(self) -> None:
        await self.engine.dispose()


def create_database(
    database_url: str,
    *,
    pool_size: int = DEFAULT_DATABASE_POOL_SIZE,
    pool_max_overflow: int = DEFAULT_DATABASE_POOL_MAX_OVERFLOW,
    pool_recycle_seconds: int = DEFAULT_DATABASE_POOL_RECYCLE_SECONDS,
) -> Database:
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "pool_recycle": pool_recycle_seconds,
    }

    if not _is_sqlite_database(database_url):
        engine_kwargs.update(
            {
                "pool_size": pool_size,
                "max_overflow": pool_max_overflow,
            }
        )

    engine = create_async_engine(
        database_url,
        **engine_kwargs,
    )
    return Database(
        engine=engine,
        session_factory=async_sessionmaker(engine, expire_on_commit=False),
    )


def create_session_factory(
    database_url: str,
    *,
    pool_size: int = DEFAULT_DATABASE_POOL_SIZE,
    pool_max_overflow: int = DEFAULT_DATABASE_POOL_MAX_OVERFLOW,
    pool_recycle_seconds: int = DEFAULT_DATABASE_POOL_RECYCLE_SECONDS,
) -> async_sessionmaker[AsyncSession]:
    return create_database(
        database_url,
        pool_size=pool_size,
        pool_max_overflow=pool_max_overflow,
        pool_recycle_seconds=pool_recycle_seconds,
    ).session_factory


def _is_sqlite_database(database_url: str) -> bool:
    return make_url(database_url).drivername.startswith("sqlite")
