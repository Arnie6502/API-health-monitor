"""Prometheus /metrics endpoint.

Exposes:
  * ahm_check_latency_ms{endpoint,}        — last latency per endpoint (gauge)
  * ahm_check_total{endpoint,}             — total checks (counter, derived)
  * ahm_check_success_total{endpoint,}     — successful checks (counter, derived)
  * ahm_check_fail_total{endpoint,}        — failed checks (counter, derived)
  * ahm_up{endpoint,}                      — 1 if last check succeeded else 0
  * ahm_alerts_open                        — currently open alerts (gauge)
  * ahm_alerts_total                       — all-time alerts (gauge/counter)

Hand-rolled text exposition so Grafana can scrape it with zero extra deps.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import AsyncSessionLocal
from ..models import Alert, Check, Endpoint

router = APIRouter(tags=["metrics"])


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def _fmt(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in labels.items())
    return "{" + inner + "}"


PROM_MEDIA_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/metrics")
async def metrics(session: AsyncSession = Depends(get_session)) -> PlainTextResponse:
    endpoints = list(
        (await session.execute(select(Endpoint))).scalars().all()
    )

    # Latest check per endpoint.
    latest: dict[int, Check] = {}
    for ep in endpoints:
        chk = (
            await session.execute(
                select(Check)
                .where(Check.endpoint_id == ep.id)
                .order_by(Check.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if chk:
            latest[ep.id] = chk

    # Aggregate counters per endpoint.
    totals: dict[int, dict[str, int]] = {}
    for ep in endpoints:
        total = await session.scalar(
            select(func.count(Check.id)).where(Check.endpoint_id == ep.id)
        ) or 0
        ok = await session.scalar(
            select(func.count(Check.id)).where(
                Check.endpoint_id == ep.id, Check.success.is_(True)
            )
        ) or 0
        totals[ep.id] = {"total": total, "ok": ok, "fail": total - ok}

    open_alerts = await session.scalar(
        select(func.count(Alert.id)).where(Alert.resolved.is_(False))
    ) or 0
    all_alerts = await session.scalar(select(func.count(Alert.id))) or 0

    lines: list[str] = []

    # --- latency gauge -----------------------------------------------------
    lines.append("# HELP ahm_check_latency_ms Last recorded latency in milliseconds.")
    lines.append("# TYPE ahm_check_latency_ms gauge")
    for ep in endpoints:
        chk = latest.get(ep.id)
        val = chk.latency_ms if chk else 0.0
        lines.append(f'ahm_check_latency_ms{_fmt({"endpoint": ep.name})} {val}')

    # --- up gauge ----------------------------------------------------------
    lines.append("# HELP ahm_up 1 if the last check for the endpoint succeeded, else 0.")
    lines.append("# TYPE ahm_up gauge")
    for ep in endpoints:
        chk = latest.get(ep.id)
        val = 1 if (chk and chk.success) else 0
        lines.append(f'ahm_up{_fmt({"endpoint": ep.name})} {val}')

    # --- check counters ----------------------------------------------------
    lines.append("# HELP ahm_check_total Total number of checks performed.")
    lines.append("# TYPE ahm_check_total counter")
    for ep in endpoints:
        lines.append(
            f'ahm_check_total{_fmt({"endpoint": ep.name})} {totals[ep.id]["total"]}'
        )

    lines.append("# HELP ahm_check_success_total Total successful checks.")
    lines.append("# TYPE ahm_check_success_total counter")
    for ep in endpoints:
        lines.append(
            f'ahm_check_success_total{_fmt({"endpoint": ep.name})} {totals[ep.id]["ok"]}'
        )

    lines.append("# HELP ahm_check_fail_total Total failed checks.")
    lines.append("# TYPE ahm_check_fail_total counter")
    for ep in endpoints:
        lines.append(
            f'ahm_check_fail_total{_fmt({"endpoint": ep.name})} {totals[ep.id]["fail"]}'
        )

    # --- alert gauges ------------------------------------------------------
    lines.append("# HELP ahm_alerts_open Number of currently open (unresolved) alerts.")
    lines.append("# TYPE ahm_alerts_open gauge")
    lines.append(f"ahm_alerts_open {open_alerts}")

    lines.append("# HELP ahm_alerts_total Total alerts ever raised.")
    lines.append("# TYPE ahm_alerts_total counter")
    lines.append(f"ahm_alerts_total {all_alerts}")

    body = "\n".join(lines) + "\n"
    return PlainTextResponse(content=body, media_type=PROM_MEDIA_TYPE)
