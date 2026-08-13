"""Tests for the alert evaluation logic — the core incident-response story."""
from datetime import UTC

import pytest
from sqlalchemy import select

from app.models import Alert, Check, Endpoint
from app.services.alerting import evaluate_and_act

pytestmark = pytest.mark.asyncio


async def _add_check(session, endpoint, *, success, minutes_ago=0):
    from datetime import datetime, timedelta

    chk = Check(
        endpoint_id=endpoint.id,
        timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        status_code=200 if success else 500,
        latency_ms=120.0 if success else 3000.0,
        success=success,
        error=None if success else "fail",
    )
    session.add(chk)
    await session.flush()
    return chk


async def _make_endpoint(session, name="svc-a"):
    ep = Endpoint(name=name, url="https://example.com/health")
    session.add(ep)
    await session.flush()
    return ep


async def test_no_alert_below_threshold(session):
    """2 failures (< threshold 3) must NOT raise an alert."""
    ep = await _make_endpoint(session)
    # Two failures, then a success — only 2 consecutive, below threshold.
    await _add_check(session, ep, success=False, minutes_ago=2)
    await _add_check(session, ep, success=False, minutes_ago=1)
    latest = await _add_check(session, ep, success=True, minutes_ago=0)
    await session.commit()

    decision = await evaluate_and_act(session, ep, latest)
    await session.commit()

    assert decision.should_alert is False
    assert decision.consecutive_failures == 0  # last check succeeded
    alerts = (await session.execute(select(Alert))).scalars().all()
    assert alerts == []


async def test_alert_after_three_consecutive_failures(session):
    """3 consecutive failures should create exactly one Alert."""
    ep = await _make_endpoint(session)
    await _add_check(session, ep, success=False, minutes_ago=2)
    await _add_check(session, ep, success=False, minutes_ago=1)
    latest = await _add_check(session, ep, success=False, minutes_ago=0)
    await session.commit()

    decision = await evaluate_and_act(session, ep, latest)
    await session.commit()

    assert decision.should_alert is True
    assert decision.consecutive_failures == 3
    alerts = (await session.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].resolved is False
    assert alerts[0].consecutive_failures == 3


async def test_no_duplicate_alert_while_still_failing(session):
    """Once an alert is open, continued failures must not create a 2nd alert."""
    ep = await _make_endpoint(session)
    for i in range(4):
        await _add_check(session, ep, success=False, minutes_ago=4 - i)
    await session.commit()
    latest = (
        await session.execute(
            select(Check).where(Check.endpoint_id == ep.id).order_by(Check.timestamp.desc()).limit(1)
        )
    ).scalar_one()
    await evaluate_and_act(session, ep, latest)
    await session.commit()

    # Another failure.
    new = await _add_check(session, ep, success=False)
    await session.commit()
    decision = await evaluate_and_act(session, ep, new)
    await session.commit()

    assert decision.should_alert is False
    alerts = (await session.execute(select(Alert))).scalars().all()
    assert len(alerts) == 1


async def test_alert_resolved_on_recovery(session):
    """A successful check after an open alert must resolve it."""
    ep = await _make_endpoint(session)
    for i in range(4):
        await _add_check(session, ep, success=False, minutes_ago=4 - i)
    await session.commit()
    failing = (
        await session.execute(
            select(Check).where(Check.endpoint_id == ep.id).order_by(Check.timestamp.desc()).limit(1)
        )
    ).scalar_one()
    await evaluate_and_act(session, ep, failing)
    await session.commit()

    # Recovery.
    ok = await _add_check(session, ep, success=True)
    await session.commit()
    decision = await evaluate_and_act(session, ep, ok)
    await session.commit()

    assert decision.should_resolve is True
    alert = (await session.execute(select(Alert))).scalar_one()
    assert alert.resolved is True
    assert alert.resolved_at is not None


async def test_success_with_no_open_alert_is_noop(session):
    """A success when nothing is alerting should do nothing."""
    ep = await _make_endpoint(session)
    ok = await _add_check(session, ep, success=True)
    await session.commit()
    decision = await evaluate_and_act(session, ep, ok)
    await session.commit()
    assert decision.should_alert is False
    assert decision.should_resolve is False
    assert (await session.execute(select(Alert))).scalars().all() == []
