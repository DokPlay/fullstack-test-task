from __future__ import annotations

from httpx import AsyncClient


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
