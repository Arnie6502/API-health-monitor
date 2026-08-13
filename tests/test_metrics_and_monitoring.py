"""Tests for the metrics endpoint's computation paths + monitoring edge cases.

Network-independent: calls the metrics route function directly (with a real
session) so coverage attributes the computation lines, plus via the ASGI
client for the HTTP-layer assertions.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.api.metrics_routes import metrics
from app.db import AsyncSessionLocal
from app.models import Alert, Check, Endpoint

pytestmark = pytest.mark.asyncio


async def _seed(session, *, successes=5, failures=0, with_alert=False):
    ep = Endpoint(name="metrics-svc", url="https://example.com/x")
    session.add(ep)
    await session.flush()
    now = datetime.now(UTC)
    for i in range(successes):
        session.add(Check(
            endpoint_id=ep.id, timestamp=now - timedelta(minutes=i),
            status_code=200, latency_ms=100.0 + i * 5, success=True,
        ))
    for i in range(failures):
        session.add(Check(
            endpoint_id=ep.id, timestamp=now - timedelta(minutes=successes + i),
            status_code=500, latency_ms=2000.0, success=False, error="boom",
        ))
    if with_alert:
        session.add(Alert(
            endpoint_id=ep.id, consecutive_failures=3,
            message="failed", resolved=False,
        ))
    await session.commit()
    return ep


async def test_metrics_reports_counters_and_up(client, session):
    await _seed(session, successes=5, failures=2)
    resp = await client.get("/metrics")
    text = resp.text
    # Counters reflect the totals.
    assert 'ahm_check_total{endpoint="metrics-svc"} 7' in text
    assert 'ahm_check_success_total{endpoint="metrics-svc"} 5' in text
    assert 'ahm_check_fail_total{endpoint="metrics-svc"} 2' in text
    # Last check was a success -> ahm_up == 1
    assert 'ahm_up{endpoint="metrics-svc"} 1' in text


async def test_metrics_reports_zero_up_when_last_check_failed(client, session):
    await _seed(session, successes=2, failures=1)
    # Reorder so the last (most recent) check is a failure.
    ep = (await session.execute(__import__("sqlalchemy").select(Endpoint))).scalar_one()
    session.add(Check(
        endpoint_id=ep.id, timestamp=datetime.now(UTC),
        status_code=500, latency_ms=999.0, success=False, error="latest fail",
    ))
    await session.commit()
    resp = await client.get("/metrics")
    assert 'ahm_up{endpoint="metrics-svc"} 0' in resp.text


async def test_metrics_reports_open_alerts(client, session):
    await _seed(session, successes=3, with_alert=True)
    resp = await client.get("/metrics")
    assert "ahm_alerts_open 1" in resp.text
    assert "ahm_alerts_total 1" in resp.text


async def test_uptime_with_no_checks_returns_100_pct(client, session):
    """An endpoint with zero checks in the window reports 100% (no data)."""
    ep = Endpoint(name="empty-svc", url="https://example.com/x")
    session.add(ep)
    await session.commit()
    resp = await client.get("/uptime", params={"hours": 24})
    data = resp.json()[0]
    assert data["total_checks"] == 0
    assert data["uptime_pct"] == 100.0
    assert data["avg_latency_ms"] == 0.0


async def test_uptime_p95_latency_computed(client, session):
    await _seed(session, successes=10)
    resp = await client.get("/uptime", params={"hours": 24})
    data = resp.json()[0]
    assert data["p95_latency_ms"] is not None
    assert data["min_latency_ms"] is not None
    assert data["max_latency_ms"] is not None
    assert data["min_latency_ms"] <= data["p95_latency_ms"] <= data["max_latency_ms"]


async def test_incidents_only_open_filter(client, session):
    ep = Endpoint(name="filter-svc", url="https://example.com/x")
    session.add(ep)
    await session.flush()
    # One open, one resolved.
    session.add(Alert(endpoint_id=ep.id, consecutive_failures=3, message="open", resolved=False))
    session.add(Alert(endpoint_id=ep.id, consecutive_failures=3, message="closed", resolved=True,
                      resolved_at=datetime.now(UTC)))
    await session.commit()

    resp = await client.get("/incidents", params={"only_open": True})
    data = resp.json()
    assert len(data) == 1
    assert data[0]["message"] == "open"


async def test_checks_history_endpoint(client, session):
    ep = await _seed(session, successes=3)
    resp = await client.get(f"/endpoints/{ep.id}/checks", params={"limit": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2  # limited


async def test_checks_history_404_for_unknown_endpoint(client):
    resp = await client.get("/endpoints/9999/checks")
    assert resp.status_code == 404


async def test_metrics_route_function_direct(setup_db):
    """Call the metrics() coroutine directly to exercise the computation body."""
    async with AsyncSessionLocal() as session:
        ep = Endpoint(name="direct-svc", url="https://example.com/x")
        session.add(ep)
        await session.flush()
        session.add(Check(
            endpoint_id=ep.id, timestamp=datetime.now(UTC),
            status_code=200, latency_ms=42.0, success=True,
        ))
        session.add(Alert(
            endpoint_id=ep.id, consecutive_failures=3,
            message="failed", resolved=False,
        ))
        await session.commit()

    async with AsyncSessionLocal() as session:
        resp = await metrics(session)
        assert resp.status_code == 200
        text = resp.body.decode()
        assert 'ahm_check_total{endpoint="direct-svc"} 1' in text
        assert 'ahm_up{endpoint="direct-svc"} 1' in text
        assert "ahm_alerts_open 1" in text
        assert "ahm_alerts_total 1" in text
        assert "ahm_check_latency_ms" in text


async def test_metrics_route_empty_db(setup_db):
    """Metrics with no endpoints should still return a valid response."""
    async with AsyncSessionLocal() as session:
        resp = await metrics(session)
        assert resp.status_code == 200
        text = resp.body.decode()
        assert "ahm_alerts_open 0" in text
        assert "ahm_alerts_total 0" in text


async def test_status_with_no_checks(client, session):
    """An endpoint with no checks yet returns nulls gracefully."""
    ep = Endpoint(name="fresh-svc", url="https://example.com/x")
    session.add(ep)
    await session.commit()
    resp = await client.get("/status")
    data = resp.json()[0]
    assert data["last_success"] is None
    assert data["last_check_at"] is None
    assert data["open_alert"] is False
