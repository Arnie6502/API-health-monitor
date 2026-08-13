"""Performs an HTTP health check against a single endpoint.

Isolated from the scheduler so it can be unit-tested directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..config import settings
from ..models import Endpoint


@dataclass
class CheckResult:
    """Outcome of a single health check."""

    status_code: int | None
    latency_ms: float
    success: bool
    error: str | None = None


async def perform_check(endpoint: Endpoint) -> CheckResult:
    """Hit ``endpoint`` once and return a :class:`CheckResult`.

    A check is considered *successful* when:
      * the HTTP request completes within the timeout, AND
      * the response status code equals ``endpoint.expected_status``.

    Any exception (timeout, DNS, connection refused, non-matching status)
    yields ``success=False`` with the error captured for storage.
    """
    start = time.perf_counter()
    method = (endpoint.method or "GET").upper()
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.request(method, endpoint.url)
        latency_ms = (time.perf_counter() - start) * 1000.0
        success = response.status_code == endpoint.expected_status
        error = None if success else (
            f"Unexpected status {response.status_code} "
            f"(expected {endpoint.expected_status})"
        )
        return CheckResult(
            status_code=response.status_code,
            latency_ms=round(latency_ms, 2),
            success=success,
            error=error,
        )
    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return CheckResult(
            status_code=None,
            latency_ms=round(latency_ms, 2),
            success=False,
            error="Request timed out",
        )
    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return CheckResult(
            status_code=None,
            latency_ms=round(latency_ms, 2),
            success=False,
            error=f"HTTP error: {exc.__class__.__name__}: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive
        latency_ms = (time.perf_counter() - start) * 1000.0
        return CheckResult(
            status_code=None,
            latency_ms=round(latency_ms, 2),
            success=False,
            error=f"Unexpected error: {exc.__class__.__name__}: {exc}",
        )
