from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.pagination import DEFAULT_PAGE_LIMIT
from src.models import Alert
from src.repositories.alerts import AlertRepository


class AlertService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        repository: AlertRepository | None = None,
    ):
        self.session_factory = session_factory
        self.repository = repository or AlertRepository()

    async def list_alerts(
        self,
        *,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> list[Alert]:
        async with self.session_factory() as session:
            return await self.repository.list(session, offset=offset, limit=limit)
