from __future__ import annotations

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch


async def test_cors_preflight_uses_explicit_method_and_header_allowlists(client: AsyncClient) -> None:
    allowed_response = await client.options(
        "/files",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert allowed_response.status_code == 200
    assert {
        method.strip()
        for method in allowed_response.headers["access-control-allow-methods"].split(",")
    } == {"GET", "POST", "PATCH", "DELETE"}

    rejected_response = await client.options(
        "/files",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "x-debug-header",
        },
    )
    assert rejected_response.status_code == 400


@pytest.mark.asyncio
async def test_health_and_metrics_endpoints(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _healthy(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr("src.api.router._check_database_ready", _healthy)
    monkeypatch.setattr("src.api.router._check_redis_ready", _healthy)

    health_live = await client.get("/health/live")
    assert health_live.status_code == 200
    assert health_live.json() == {"status": "ok"}

    health_ready = await client.get("/health/ready")
    assert health_ready.status_code == 200
    assert health_ready.json() == {
        "status": "ready",
        "checks": {"database": True, "redis": True},
    }

    health_alias = await client.get("/health")
    assert health_alias.status_code == 200
    assert health_alias.json() == health_ready.json()

    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "http_requests_total" in metrics_response.text


@pytest.mark.asyncio
async def test_readiness_reports_dependency_failures(
    client: AsyncClient,
    monkeypatch: MonkeyPatch,
) -> None:
    async def _database_down(*_args, **_kwargs) -> bool:
        return False

    async def _redis_healthy(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr("src.api.router._check_database_ready", _database_down)
    monkeypatch.setattr("src.api.router._check_redis_ready", _redis_healthy)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "unhealthy",
            "checks": {"database": False, "redis": True},
        },
    }
