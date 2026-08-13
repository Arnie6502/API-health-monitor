"""FastAPI application — wires routers, lifespan (DB init + scheduler)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import endpoints_routes, metrics_routes, monitoring_routes
from .config import settings
from .services.init import init_db, seed_bootstrap_endpoints
from .services.scheduler import poll_all_endpoints, start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("api_health_monitor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup -----------------------------------------------------------
    await init_db()
    await seed_bootstrap_endpoints()
    # Run one poll immediately so /status has data right away.
    await poll_all_endpoints()
    if settings.scheduler_enabled:
        start_scheduler()
    logger.info("API Health Monitor ready at interval=%ss", settings.poll_interval_seconds)
    try:
        yield
    finally:
        # --- Shutdown ------------------------------------------------------
        stop_scheduler()
        logger.info("API Health Monitor stopped.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="API Health Monitor",
        description=(
            "A small backend service that periodically polls your existing "
            "APIs, records status/latency/uptime, and alerts on consecutive "
            "failures. Exposes Prometheus metrics for Grafana."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(endpoints_routes.router)
    app.include_router(monitoring_routes.router)
    app.include_router(metrics_routes.router)

    @app.get("/", tags=["root"])
    async def root():
        return {
            "service": "API Health Monitor",
            "version": "1.0.0",
            "docs": "/docs",
            "metrics": "/metrics",
            "endpoints": ["/status", "/uptime", "/incidents", "/endpoints"],
        }

    return app


app = create_app()
