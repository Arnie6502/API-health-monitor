"""Alert evaluation: 3 consecutive failures -> create Alert + fire webhook.

The alert logic is deliberately pure-ish and operates on the most recent N
checks for an endpoint so it can be unit-tested without time travel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Alert, Check, Endpoint

logger = logging.getLogger("api_health_monitor.alerting")


@dataclass
class AlertDecision:
    """What the alert evaluator decided to do for an endpoint."""

    should_alert: bool
    should_resolve: bool
    consecutive_failures: int


async def _latest_alert_for_endpoint(
    session: AsyncSession, endpoint_id: int
) -> Alert | None:
    stmt = (
        select(Alert)
        .where(Alert.endpoint_id == endpoint_id)
        .order_by(Alert.triggered_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def evaluate_and_act(
    session: AsyncSession,
    endpoint: Endpoint,
    last_check: Check,
) -> AlertDecision:
    """Apply the consecutive-failure alert rule for ``endpoint``.

    Rules:
      * If the last ``threshold`` checks all failed AND there is no open
        alert -> create a new Alert and fire the webhook.
      * If the last check succeeded AND there is an open alert -> mark it
        resolved.
      * Otherwise -> no-op.

    Returns an :class:`AlertDecision` describing what happened (useful for
    tests and logging).
    """
    threshold = settings.consecutive_failures_threshold

    # Pull the most recent `threshold` checks to count consecutive failures.
    stmt = (
        select(Check)
        .where(Check.endpoint_id == endpoint.id)
        .order_by(Check.timestamp.desc())
        .limit(threshold)
    )
    result = await session.execute(stmt)
    recent = list(result.scalars().all())

    consecutive_failures = 0
    for chk in recent:
        if not chk.success:
            consecutive_failures += 1
        else:
            break

    latest_alert = await _latest_alert_for_endpoint(session, endpoint.id)
    open_alert = latest_alert if (latest_alert and not latest_alert.resolved) else None

    decision = AlertDecision(
        should_alert=False,
        should_resolve=False,
        consecutive_failures=consecutive_failures,
    )

    # --- Fire an alert ------------------------------------------------------
    if consecutive_failures >= threshold and open_alert is None:
        message = (
            f"Endpoint '{endpoint.name}' ({endpoint.url}) failed "
            f"{consecutive_failures} consecutive checks"
        )
        alert = Alert(
            endpoint_id=endpoint.id,
            consecutive_failures=consecutive_failures,
            message=message,
            resolved=False,
        )
        session.add(alert)
        await session.flush()  # populate alert.id
        alert.webhook_sent = await fire_webhook(endpoint, alert)
        decision.should_alert = True
        logger.warning("ALERT raised: %s", message)

    # --- Resolve an existing alert -----------------------------------------
    elif last_check.success and open_alert is not None:
        from datetime import datetime

        open_alert.resolved = True
        open_alert.resolved_at = datetime.now(UTC)
        decision.should_resolve = True
        logger.info("ALERT resolved for endpoint '%s'", endpoint.name)

    return decision


async def fire_webhook(endpoint: Endpoint, alert: Alert) -> bool:
    """POST the alert payload to the configured webhook URL, if any.

    Returns True if a webhook was configured and the POST succeeded (2xx),
    False otherwise. Failures are logged but never raise — alerting must
    not break monitoring.
    """
    url = settings.alert_webhook_url
    if not url:
        return False

    payload = {
        "endpoint": endpoint.name,
        "url": endpoint.url,
        "consecutive_failures": alert.consecutive_failures,
        "message": alert.message,
        "triggered_at": alert.triggered_at.isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        if 200 <= resp.status_code < 300:
            logger.info("Webhook delivered to %s", url)
            return True
        logger.warning("Webhook returned %s", resp.status_code)
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("Webhook delivery failed: %s", exc)
    return False
