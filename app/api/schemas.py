"""Pydantic schemas for the REST API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    url: str
    method: str
    expected_status: int
    interval_seconds: int
    enabled: bool


class EndpointCreate(BaseModel):
    name: str
    url: str
    method: str = "GET"
    expected_status: int = 200
    interval_seconds: int = 60
    enabled: bool = True


class CurrentStatus(BaseModel):
    """Current status of a single endpoint, with its latest check."""
    endpoint: EndpointOut
    last_check_at: datetime | None = None
    last_status_code: int | None = None
    last_latency_ms: float | None = None
    last_success: bool | None = None
    last_error: str | None = None
    open_alert: bool = False


class UptimeReport(BaseModel):
    """Uptime % and average latency over a rolling window."""
    endpoint: EndpointOut
    window_hours: int
    total_checks: int
    successful_checks: int
    uptime_pct: float
    avg_latency_ms: float
    min_latency_ms: float | None = None
    max_latency_ms: float | None = None
    p95_latency_ms: float | None = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    endpoint_id: int
    endpoint_name: str = ""
    triggered_at: datetime
    resolved_at: datetime | None = None
    resolved: bool
    consecutive_failures: int
    message: str
    webhook_sent: bool


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    endpoint_id: int
    timestamp: datetime
    status_code: int | None
    latency_ms: float
    success: bool
    error: str | None = None
