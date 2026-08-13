"""Tests for the poller (HTTP check) + recording logic.

Network-dependent tests use reliable public endpoints; status-code edge
cases use a local mock server so they're deterministic.
"""
from datetime import UTC

import pytest
from sqlalchemy import select

from app.models import Check, Endpoint
from app.services.poller import perform_check

pytestmark = pytest.mark.asyncio


async def test_perform_check_success_against_real_endpoint():
    """Hits a reliable public 200 endpoint. Success path."""
    ep = Endpoint(
        name="open-meteo",
        url="https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current=temperature_2m",
        expected_status=200,
    )
    result = await perform_check(ep)
    assert result.success is True
    assert result.status_code == 200
    assert result.latency_ms > 0
    assert result.error is None


async def test_perform_check_unexpected_status(mock_404_server):
    """A 404 when 200 is expected is a failure, not an exception."""
    ep = Endpoint(name="svc404", url=mock_404_server, expected_status=200)
    result = await perform_check(ep)
    assert result.success is False
    assert result.status_code == 404
    assert "Unexpected status" in (result.error or "")


async def test_perform_check_matching_status(mock_404_server):
    """When expected_status matches the actual code, it's a success."""
    ep = Endpoint(name="svc404ok", url=mock_404_server, expected_status=404)
    result = await perform_check(ep)
    assert result.success is True
    assert result.status_code == 404


async def test_perform_check_unreachable_host():
    """A non-routable host yields a graceful failure, not a crash."""
    ep = Endpoint(name="dead", url="http://10.255.255.1:80/", expected_status=200)
    result = await perform_check(ep)
    assert result.success is False
    assert result.status_code is None
    assert result.error is not None
    assert result.latency_ms >= 0


async def test_check_recorded_with_all_fields(session, mock_200_server):
    """A Check row persists timestamp, status, latency, success."""
    from datetime import datetime

    ep = Endpoint(name="svc", url=mock_200_server, expected_status=200)
    session.add(ep)
    await session.flush()

    result = await perform_check(ep)
    session.add(
        Check(
            endpoint_id=ep.id,
            timestamp=datetime.now(UTC),
            status_code=result.status_code,
            latency_ms=result.latency_ms,
            success=result.success,
            error=result.error,
        )
    )
    await session.commit()

    chk = (await session.execute(select(Check))).scalar_one()
    assert chk.success is True
    assert chk.status_code == 200
    assert chk.latency_ms > 0
    assert chk.endpoint_id == ep.id
