"""Database lifecycle helpers: create tables, seed bootstrap endpoints."""
from __future__ import annotations

import logging

from sqlalchemy import select

from ..config import settings
from ..db import AsyncSessionLocal, Base, engine
from ..models import Endpoint

logger = logging.getLogger("api_health_monitor.db")


async def init_db() -> None:
    """Create all tables (idempotent). For SQLite this is all you need;
    in production prefer Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured.")


async def seed_bootstrap_endpoints() -> None:
    """Insert the bootstrap endpoints if they don't already exist."""
    async with AsyncSessionLocal() as session:
        for name, url in settings.parsed_bootstrap_endpoints:
            exists = await session.scalar(
                select(Endpoint).where(Endpoint.name == name)
            )
            if exists is None:
                session.add(Endpoint(name=name, url=url))
                logger.info("Seeded endpoint: %s -> %s", name, url)
        await session.commit()
