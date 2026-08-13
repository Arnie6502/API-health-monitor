"""Tests for the scheduler tick (poll_all_endpoints) end-to-end."""
import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Check, Endpoint
from app.services.scheduler import poll_all_endpoints

pytestmark = pytest.mark.asyncio


async def test_poll_all_writes_checks_for_each_endpoint(setup_db):
    """poll_all_endpoints should write one Check per enabled endpoint."""
    async with AsyncSessionLocal() as session:
        session.add(Endpoint(name="ep-1", url="https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m"))
        session.add(Endpoint(name="ep-2", url="https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35&current=temperature_2m"))
        await session.commit()

    await poll_all_endpoints()

    async with AsyncSessionLocal() as session:
        checks = (await session.execute(select(Check))).scalars().all()
        assert len(checks) == 2
        ep_ids = {c.endpoint_id for c in checks}
        endpoints = (await session.execute(select(Endpoint))).scalars().all()
        assert ep_ids == {e.id for e in endpoints}
        # All should be successes against the real open-meteo API.
        assert all(c.latency_ms > 0 for c in checks)


async def test_poll_all_skips_disabled_endpoints(setup_db):
    """Disabled endpoints must not be polled."""
    async with AsyncSessionLocal() as session:
        session.add(Endpoint(name="enabled-ep", url="https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m", enabled=True))
        session.add(Endpoint(name="disabled-ep", url="https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35&current=temperature_2m", enabled=False))
        await session.commit()

    await poll_all_endpoints()

    async with AsyncSessionLocal() as session:
        checks = (await session.execute(select(Check))).scalars().all()
        assert len(checks) == 1
        ep = (await session.execute(select(Endpoint).where(Endpoint.name == "enabled-ep"))).scalar_one()
        assert checks[0].endpoint_id == ep.id


async def test_poll_all_no_endpoints_is_noop(setup_db):
    """With zero endpoints, polling should not raise."""
    await poll_all_endpoints()  # no endpoints configured
    async with AsyncSessionLocal() as session:
        checks = (await session.execute(select(Check))).scalars().all()
        assert checks == []
