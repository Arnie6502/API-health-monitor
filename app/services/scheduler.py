"""Scheduler: periodically polls every enabled endpoint and records results.

Uses APScheduler so the whole thing runs in-process with the API server —
no separate celery/redis worker required for v1, though the design is
worker-friendly (the polling function is importable and idempotent).

The scheduler is started as a FastAPI lifespan task and can also be driven
by a management/console entry point (see ``app.cli``).
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from ..db import AsyncSessionLocal
from ..models import Check, Endpoint
from .alerting import evaluate_and_act
from .poller import perform_check

logger = logging.getLogger("api_health_monitor.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def poll_all_endpoints() -> None:
    """One scheduler tick: poll every enabled endpoint and persist results.

    Endpoints are polled concurrently for speed. Each result is stored, then
    the alert rule is evaluated for that endpoint.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Endpoint).where(Endpoint.enabled.is_(True))
        endpoints = list((await session.execute(stmt)).scalars().all())

    if not endpoints:
        logger.debug("No enabled endpoints to poll.")
        return

    logger.info("Polling %d endpoint(s)", len(endpoints))

    async def _poll_one(ep: Endpoint) -> None:
        result = await perform_check(ep)
        async with AsyncSessionLocal() as session:
            # Re-fetch the endpoint within this session to avoid detached state.
            endpoint = await session.get(Endpoint, ep.id)
            if endpoint is None:
                return
            check = Check(
                endpoint_id=endpoint.id,
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                success=result.success,
                error=result.error,
            )
            session.add(check)
            await session.flush()
            await evaluate_and_act(session, endpoint, check)
            await session.commit()
        logger.info(
            "Check %s -> success=%s status=%s latency=%.1fms",
            ep.name, result.success, result.status_code, result.latency_ms,
        )

    await asyncio.gather(*(_poll_one(ep) for ep in endpoints), return_exceptions=True)


def get_scheduler() -> AsyncIOScheduler:
    """Return (and lazily create) the global AsyncIO scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler(interval_seconds: int | None = None) -> AsyncIOScheduler:
    """Start the scheduler, polling every ``interval_seconds``."""
    from ..config import settings

    sched = get_scheduler()
    interval = interval_seconds or settings.poll_interval_seconds
    sched.add_job(
        poll_all_endpoints,
        "interval",
        seconds=interval,
        id="poll_all_endpoints",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if not sched.running:
        sched.start()
    logger.info("Scheduler started (interval=%ss)", interval)
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
