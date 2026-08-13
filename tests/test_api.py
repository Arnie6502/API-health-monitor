"""Tests for the read/query API: /status, /uptime, /incidents."""
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Alert, Check, Endpoint

pytestmark = pytest.mark.asyncio


async def _seed_basic(session):
    ep = Endpoint(name="demo", url="https://example.com/health")
    session.add(ep)
    await session.flush()
    now = datetime.now(UTC)
    # 8 successes, 2 failures over the window.
    for i in range(8):
        session.add(
            Check(
                endpoint_id=ep.id,
                timestamp=now - timedelta(minutes=i),
                status_code=200,
                latency_ms=100 + i,
                success=True,
            )
        )
    for i in range(2):
        session.add(
            Check(
                endpoint_id=ep.id,
                timestamp=now - timedelta(minutes=8 + i),
                status_code=500,
                latency_ms=999,
                success=False,
                error="boom",
            )
        )
    await session.commit()
    return ep


async def test_status_endpoint_returns_latest_check(client, session):
    await _seed_basic(session)
    resp = await client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["endpoint"]["name"] == "demo"
    assert data[0]["last_success"] is True


async def test_uptime_endpoint_computes_percentage(client, session):
    await _seed_basic(session)
    resp = await client.get("/uptime", params={"hours": 24})
    assert resp.status_code == 200
    data = resp.json()[0]
    assert data["total_checks"] == 10
    assert data["successful_checks"] == 8
    assert data["uptime_pct"] == 80.0
    assert data["avg_latency_ms"] > 0


async def test_incidents_endpoint_lists_alerts(client, session):
    ep = Endpoint(name="incident-svc", url="https://example.com/x")
    session.add(ep)
    await session.flush()
    session.add(
        Alert(
            endpoint_id=ep.id,
            consecutive_failures=3,
            message="Endpoint failed 3 times",
            resolved=False,
        )
    )
    await session.commit()

    resp = await client.get("/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["endpoint_name"] == "incident-svc"
    assert data[0]["resolved"] is False


async def test_endpoints_crud(client):
    resp = await client.post(
        "/endpoints",
        json={"name": "new-svc", "url": "https://example.com/ping"},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "new-svc"

    resp = await client.get("/endpoints")
    assert resp.status_code == 200
    assert any(e["name"] == "new-svc" for e in resp.json())

    resp = await client.delete(f"/endpoints/{created['id']}")
    assert resp.status_code == 204


async def test_metrics_endpoint_prometheus_format(client, session):
    await _seed_basic(session)
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "ahm_up" in resp.text
    assert "ahm_check_latency_ms" in resp.text
    assert resp.headers["content-type"].startswith("text/plain")
