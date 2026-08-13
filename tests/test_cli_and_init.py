"""Tests for the CLI commands and DB init/seed service."""
import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Alert, Check, Endpoint
from app.services.init import init_db, seed_bootstrap_endpoints

pytestmark = pytest.mark.asyncio


async def test_init_db_creates_tables(setup_db):
    # setup_db already creates then drops; calling init_db again is idempotent.
    await init_db()
    async with AsyncSessionLocal() as session:
        session.add(Endpoint(name="t", url="https://e.com"))
        await session.commit()
        assert (await session.execute(select(Endpoint))).scalar_one().name == "t"


async def test_seed_bootstrap_endpoints_inserts_defaults(setup_db):
    await seed_bootstrap_endpoints()
    async with AsyncSessionLocal() as session:
        names = [e.name for e in (await session.execute(select(Endpoint))).scalars().all()]
        assert "Weather API" in names
        assert "HTTPBin" in names


async def test_seed_bootstrap_endpoints_is_idempotent(setup_db):
    await seed_bootstrap_endpoints()
    await seed_bootstrap_endpoints()  # second call must not duplicate
    async with AsyncSessionLocal() as session:
        count = len((await session.execute(select(Endpoint))).scalars().all())
        assert count == 2


async def test_cli_seed_demo_generates_history(setup_db):
    """The seed-demo command should create checks + an alert without erroring."""
    from app.cli import cmd_seed_demo
    await init_db()
    await seed_bootstrap_endpoints()
    await cmd_seed_demo()

    async with AsyncSessionLocal() as session:
        checks = (await session.execute(select(Check))).scalars().all()
        alerts = (await session.execute(select(Alert))).scalars().all()
        assert len(checks) > 1000  # 2 endpoints * 1440 checks
        assert len(alerts) >= 1
        assert any(not c.success for c in checks)
        assert any(c.success for c in checks)


async def test_cli_poll_runs_one_tick(setup_db):
    """The poll CLI command should run without error and produce checks."""
    from app.cli import cmd_poll
    await cmd_poll()
    async with AsyncSessionLocal() as session:
        checks = (await session.execute(select(Check))).scalars().all()
        assert len(checks) >= 1
