"""Status, uptime, and incidents — the read/query API."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import AsyncSessionLocal
from ..models import Alert, Check, Endpoint
from .schemas import CheckOut, CurrentStatus, IncidentOut, UptimeReport

router = APIRouter(tags=["monitoring"])


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# --------------------------------------------------------------------------- #
# GET /status — current status of every endpoint (latest check + open alert)
# --------------------------------------------------------------------------- #
@router.get("/status", response_model=list[CurrentStatus])
async def get_status(session: AsyncSession = Depends(get_session)):
    endpoints = list(
        (await session.execute(select(Endpoint).order_by(Endpoint.id))).scalars().all()
    )
    out: list[CurrentStatus] = []
    for ep in endpoints:
        # Latest check for this endpoint.
        latest_check = (
            await session.execute(
                select(Check)
                .where(Check.endpoint_id == ep.id)
                .order_by(Check.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        open_alert = (
            await session.scalar(
                select(func.count(Alert.id)).where(
                    Alert.endpoint_id == ep.id, Alert.resolved.is_(False)
                )
            )
        ) or 0

        out.append(
            CurrentStatus(
                endpoint=ep,
                last_check_at=latest_check.timestamp if latest_check else None,
                last_status_code=latest_check.status_code if latest_check else None,
                last_latency_ms=latest_check.latency_ms if latest_check else None,
                last_success=latest_check.success if latest_check else None,
                last_error=latest_check.error if latest_check else None,
                open_alert=bool(open_alert),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# GET /uptime?hours=24 — uptime % + latency stats over a rolling window
# --------------------------------------------------------------------------- #
def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


@router.get("/uptime", response_model=list[UptimeReport])
async def get_uptime(
    hours: int = Query(24, ge=1, le=24 * 30),
    session: AsyncSession = Depends(get_session),
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    endpoints = list(
        (await session.execute(select(Endpoint).order_by(Endpoint.id))).scalars().all()
    )
    out: list[UptimeReport] = []
    for ep in endpoints:
        rows = (
            await session.execute(
                select(Check)
                .where(Check.endpoint_id == ep.id, Check.timestamp >= since)
                .order_by(Check.timestamp.asc())
            )
        ).scalars().all()

        total = len(rows)
        successful = sum(1 for r in rows if r.success)
        latencies = [r.latency_ms for r in rows if r.success]

        out.append(
            UptimeReport(
                endpoint=ep,
                window_hours=hours,
                total_checks=total,
                successful_checks=successful,
                uptime_pct=round((successful / total) * 100, 3) if total else 100.0,
                avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
                min_latency_ms=round(min(latencies), 2) if latencies else None,
                max_latency_ms=round(max(latencies), 2) if latencies else None,
                p95_latency_ms=round(_percentile(latencies, 0.95), 2) if latencies else None,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# GET /incidents — recent alerts (open first, then most recent)
# --------------------------------------------------------------------------- #
@router.get("/incidents", response_model=list[IncidentOut])
async def get_incidents(
    limit: int = Query(50, ge=1, le=500),
    only_open: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Alert, Endpoint.name)
        .join(Endpoint, Alert.endpoint_id == Endpoint.id)
        .order_by(Alert.resolved.asc(), Alert.triggered_at.desc())
        .limit(limit)
    )
    if only_open:
        stmt = stmt.where(Alert.resolved.is_(False))
    rows = (await session.execute(stmt)).all()
    return [
        IncidentOut(
            id=alert.id,
            endpoint_id=alert.endpoint_id,
            endpoint_name=name,
            triggered_at=alert.triggered_at,
            resolved_at=alert.resolved_at,
            resolved=alert.resolved,
            consecutive_failures=alert.consecutive_failures,
            message=alert.message,
            webhook_sent=alert.webhook_sent,
        )
        for alert, name in rows
    ]


# --------------------------------------------------------------------------- #
# GET /endpoints/{id}/checks — raw check history for an endpoint
# --------------------------------------------------------------------------- #
@router.get("/endpoints/{endpoint_id}/checks", response_model=list[CheckOut])
async def get_checks(
    endpoint_id: int,
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    if await session.get(Endpoint, endpoint_id) is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    rows = (
        await session.execute(
            select(Check)
            .where(Check.endpoint_id == endpoint_id)
            .order_by(Check.timestamp.desc())
            .limit(limit)
        )
    ).scalars().all()
    return rows
