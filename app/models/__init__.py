"""ORM models for the health monitor."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Endpoint(Base):
    """A configured API endpoint to monitor.

    One row per endpoint you want watched. The scheduler reads these and
    performs an HTTP check for each, writing a ``Check`` row with the result.
    """

    __tablename__ = "endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    # How often (seconds) to poll this endpoint. The scheduler respects this.
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    checks: Mapped[list[Check]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Endpoint {self.name} {self.url}>"


class Check(Base):
    """A single recorded health-check result.

    Written once per scheduled poll per endpoint.
    """

    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    endpoint: Mapped[Endpoint] = relationship(back_populates="checks")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Check ep={self.endpoint_id} ok={self.success} {self.latency_ms}ms>"


class Alert(Base):
    """An alert raised when an endpoint fails N times in a row.

    A new Alert row is created the moment the consecutive-failure threshold
    is crossed. It is marked ``resolved`` once the endpoint recovers.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    endpoint: Mapped[Endpoint] = relationship(back_populates="alerts")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Alert ep={self.endpoint_id} resolved={self.resolved}>"
