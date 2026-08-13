"""API Health Monitor — configuration via environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AHM_",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Database -----------------------------------------------------------
    # Default to SQLite so the project runs with zero external deps.
    # Set AHM_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db
    # to switch to Postgres in Docker.
    database_url: str = "sqlite+aiosqlite:///./api_health_monitor.db"

    # --- Scheduler ----------------------------------------------------------
    poll_interval_seconds: int = 60
    scheduler_enabled: bool = True

    # --- Alerting -----------------------------------------------------------
    consecutive_failures_threshold: int = 3
    request_timeout_seconds: float = 10.0
    alert_webhook_url: str = ""

    # --- Bootstrap endpoints (comma-separated "name|url" pairs) -------------
    # Seeded into the DB on first run so the service has something to monitor.
    bootstrap_endpoints: str = (
        "Weather API|https://api.open-meteo.com/v1/forecast?"
        "latitude=52.52&longitude=13.41&current=temperature_2m,"
        "HTTPBin|https://httpbin.org/status/200"
    )

    @property
    def parsed_bootstrap_endpoints(self) -> list[tuple[str, str]]:
        endpoints: list[tuple[str, str]] = []
        for raw in self.bootstrap_endpoints.split("|,|") if "|,|" in self.bootstrap_endpoints else self.bootstrap_endpoints.split(","):
            raw = raw.strip()
            if not raw or "|" not in raw:
                continue
            name, url = raw.split("|", 1)
            endpoints.append((name.strip(), url.strip()))
        return endpoints


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
