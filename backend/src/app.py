from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import build_router
from src.core.container import ApplicationContainer, create_container
from src.core.settings import get_settings
from src.services.queue import CeleryFileProcessingQueue


ALLOWED_CORS_METHODS = ["GET", "POST", "PATCH", "DELETE"]
ALLOWED_CORS_HEADERS = ["Accept", "Authorization", "Content-Type"]


def create_app(
    *,
    container: ApplicationContainer | None = None,
) -> FastAPI:
    settings = get_settings()
    resolved_container = container or create_container(
        settings=settings,
        processing_queue=CeleryFileProcessingQueue(settings.redis_url),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await resolved_container.aclose()

    app = FastAPI(title="Secure File Exchange", lifespan=lifespan)
    app.state.container = resolved_container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=ALLOWED_CORS_METHODS,
        allow_headers=ALLOWED_CORS_HEADERS,
    )
    app.include_router(build_router())
    return app


app = create_app()
