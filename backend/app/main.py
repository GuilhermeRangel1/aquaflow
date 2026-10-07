from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import alerts, auth, consumption, resources, telemetry
from app.core.config import Settings, settings
from app.db.session import create_session_factory


def create_app(
    *,
    settings: Settings = settings,
    session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    factory = session_factory or create_session_factory(settings)
    engine: Any = getattr(factory, "kw", {}).get("bind")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
    )
    app.include_router(telemetry.router)
    app.include_router(consumption.router)
    app.include_router(auth.router)
    app.include_router(resources.router)
    app.include_router(alerts.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = exc.detail
        else:
            body = {"code": "http_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={**body, "details": {}})

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"location": error["loc"], "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "invalid_request",
                "message": "Request does not match the expected schema",
                "details": {"fields": errors},
            },
        )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


app = create_app()
