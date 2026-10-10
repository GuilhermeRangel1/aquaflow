import asyncio
from collections import Counter
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import alerts, auth, consumption, dashboard_health, ml_inferences, resources, telemetry
from app.core.config import Settings, settings
from app.db.session import create_session_factory
from app.services.device_monitor import run_offline_monitor


def create_app(
    *,
    settings: Settings = settings,
    session_factory: Callable[[], AsyncSession] | async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    factory = session_factory or create_session_factory(settings)
    engine: Any = getattr(factory, "kw", {}).get("bind")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        monitor_task = asyncio.create_task(run_offline_monitor(factory))
        app.state.offline_monitor_task = monitor_task
        try:
            yield
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
        if engine is not None:
            await engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = factory
    request_counts: Counter[tuple[str, str, int]] = Counter()

    @app.middleware("http")
    async def count_http_requests(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        request_counts[(request.method, route_template, response.status_code)] += 1
        return response

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
    app.include_router(ml_inferences.router)
    app.include_router(dashboard_health.router)

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

    @app.get("/metrics", tags=["health"], response_class=PlainTextResponse)
    async def metrics() -> PlainTextResponse:
        lines = [
            "# HELP aquaflow_http_requests_total HTTP requests handled by this API process.",
            "# TYPE aquaflow_http_requests_total counter",
        ]
        for (method, route, status), count in sorted(request_counts.items()):
            safe_route = route.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(
                f'aquaflow_http_requests_total{{method="{method}",route="{safe_route}",'
                f'status="{status}"}} {count}'
            )
        return PlainTextResponse(
            "\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return app


app = create_app()
