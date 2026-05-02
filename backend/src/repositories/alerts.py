from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Alert


class AlertRepository:
    async def list(
        self,
        session: AsyncSession,
        *,
        offset: int,
        limit: int,
    ) -> list[Alert]:
        result = await session.execute(
            select(Alert)
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_many(
        self,
        session: AsyncSession,
        alert_ids: Iterable[int],
    ) -> dict[int, Alert]:
        normalized_alert_ids = list(dict.fromkeys(alert_ids))
        if not normalized_alert_ids:
            return {}

        result = await session.execute(
            select(Alert)
            .where(Alert.id.in_(normalized_alert_ids))
            .execution_options(populate_existing=True),
        )
        return {alert.id: alert for alert in result.scalars().all()}

    def add(self, session: AsyncSession, alert: Alert) -> None:
        session.add(alert)
