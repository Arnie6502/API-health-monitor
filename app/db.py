"""Async SQLAlchemy engine + session factory.

Uses aiosqlite for SQLite and psycopg2 (sync driver wrapped) for Postgres.
The DB URL is taken from settings so the same code runs locally on SQLite
and in Docker on Postgres.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings


def _normalize_url(url: str) -> str:
    """Allow users to pass a sync-style postgres URL by converting the driver."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


engine = create_async_engine(
    _normalize_url(settings.database_url),
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
