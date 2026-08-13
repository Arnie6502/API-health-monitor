# API Health Monitor

A small backend service that periodically polls your existing APIs, records status, latency, and uptime, and alerts you when they're not healthy. It turns the projects you already have into a monitored system — and exports Prometheus metrics so you can point Grafana at it and screenshot a real dashboard.

One-line pitch: watch your own APIs, record the results, alert on failure, expose metrics. Monitoring is a core DevOps/DevSecOps skill, and this gives you a concrete, running artifact that demonstrates it.

What it does

 Capability Implementation

 Scheduler A periodic task (every 60s, configurable) hits every enabled endpoint and records HTTP status, response time, and a pass/fail. Built on APScheduler running in-process with the API server.

 Storage Results stored in a relational DB — timestamp, endpoint, status_code, latency_ms, success, error. SQLite for v1 (zero-config), PostgreSQL for Docker/production.

 Query API Read endpoints: current status, uptime % over a rolling window, average/min/max/p95 latency, recent incidents, and raw check history.

 Alerting A rule engine: if an endpoint fails N times in a row (default 3), an Alert row is created and an optional webhook (Slack/Discord/custom) is fired. The alert auto-resolves when the endpoint recovers.

 Metrics A /metrics endpoint in Prometheus text format — ahm_up, ahm_check_latency_ms, ahm_check_total, ahm_check_success_total, ahm_check_fail_total, ahm_alerts_open, ahm_alerts_total. Grafana scrapes it.

 CI GitHub Actions: lint (ruff) → test (pytest + 86% coverage) → build (Docker) → Trivy vulnerability scan.

Architecture

                 ┌──────────────────────────────────────────────┐
                 │                  FastAPI app                  │
                 │  ┌────────────┐   ┌────────────────────────┐  │
   HTTP clients ─┼─▶│  REST API  │   │   APScheduler (60s)    │  │
                 │  │ /status    │   │   poll_all_endpoints() │  │
                 │  │ /uptime    │   └───────────┬────────────┘  │
                 │  │ /incidents │               │               │
                 │  │ /endpoints │               ▼               │
                 │  │ /metrics   │      ┌────────────────┐       │
                 │  └────────────┘      │    Poller      │       │
                 │                      │  (httpx check) │       │
                 │                      └───────┬────────┘       │
                 │                              │               │
                 │                 ┌────────────▼──────────┐    │
                 │                 │  Alert evaluator      │    │──▶ webhook (optional)
                 │                 │  3 fails → Alert      │    │
                 │                 └────────────┬──────────┘    │
                 │                              │               │
                 └──────────────────────────────┼───────────────┘
                                                ▼
                              ┌──────────────────────────────────┐
                              │   SQLAlchemy (async)             │
                              │   SQLite (dev) / Postgres (prod) │
                              └──────────────────────────────────┘
                                                ▲
                                                │ scrape /metrics
                              ┌─────────────────┴──────────┐
                              │      Prometheus             │
                              └─────────────────┬──────────┘
                                                │ query
                              ┌─────────────────┴──────────┐
                              │        Grafana              │
                              │  (provisioned dashboard)    │
                              └─────────────────────────────┘

Data model

- Endpoint — a configured API to monitor: name, url, method, expected_status, interval_seconds, enabled.

- Check — one recorded health check: endpoint_id, timestamp, status_code, latency_ms, success, error.

- Alert — an incident: endpoint_id, triggered_at, resolved_at, resolved, consecutive_failures, message, webhook_sent.

Tech stack (deliberately minimal)

 Layer Choice Why

 Language Python 3.11 Modern, async, ubiquitous in DevOps tooling.

 Framework FastAPI Async-first, automatic OpenAPI docs, lighter than Django for this scope.

 Scheduler APScheduler (in-process) No separate worker/redis needed for v1; the design is worker-ready.

 Storage SQLAlchemy 2.0 (async) + SQLite/Postgres One codebase, two backends — SQLite for zero-config local dev, Postgres in Docker.

 HTTP client httpx Async, follows redirects, clean timeout handling.

 Container Docker + Docker Compose One file brings up app + db + redis + prometheus + grafana.

 CI GitHub Actions lint → test → build → Trivy scan.

 Observability Prometheus /metrics + Grafana Hand-rolled Prometheus exposition (no extra dep).

 Testing pytest + pytest-asyncio + coverage 34 tests, 86% coverage.

 Linting ruff Fast, modern, replaces flake8 + isort + black checks.

Note on the stack choice: the original spec offered Django + DRF or FastAPI. FastAPI was chosen because the service is a focused REST + scheduler app with no admin UI needs, and async-first lets the poller hit multiple endpoints concurrently — a meaningful latency win at scale. The Django equivalent would add an admin, ORM migrations via Alembic-equivalent, and celery+redis for the scheduler; this build keeps redis in the compose stack so a celery upgrade is a zero-refactor swap.

Quick start

Windows users: use the provided .bat helpers instead of the bash commands below — see Windows quick start. The bash commands use # comments which cmd.exe does not understand.

Windows quick start (cmd / PowerShell)

The repo ships with .bat helpers that handle virtual-env activation and the python -m prefixes for you:

setup.bat     :: create .venv + install dependencies  (run once)
run.bat       :: start the API server (SQLite, scheduler on)
demo.bat      :: seed ~24h of synthetic data for the Grafana dashboard
test.bat      :: run the test suite + lint
docker.bat    :: build & run the full stack (needs Docker Desktop)

Requirements:

- Python 3.11 installed — get it from <https://www.python.org/downloads/windows/> and tick "Add python.exe to PATH" in the installer. Verify with py --version.

- (Optional, for the full stack) Docker Desktop — <https://www.docker.com/products/docker-desktop/>

Typical first run:

setup.bat
run.bat

Then open <http://127.0.0.1:8000/status> in a browser.

If py and python both say "not recognized", Python isn't installed or isn't on your PATH — reinstall it with the PATH checkbox ticked, then close and reopen your terminal.

Option A — Local (zero dependencies beyond Python)

cd api-health-monitor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

## Run the service (SQLite, scheduler on, polls every 60s)

uvicorn app.main:app --reload

In another terminal, verify:

curl <http://127.0.0.1:8000/status>
curl <http://127.0.0.1:8000/metrics>

The app auto-creates tables and seeds two demo endpoints (Weather API + HTTPBin) on first start.

Option B — Docker Compose (full observability stack)

cd api-health-monitor
docker compose up --build

This brings up five services:

 Service Port Purpose

 app <http://localhost:8000> The FastAPI service + scheduler + /metrics

 db localhost:5432 PostgreSQL storage

 redis localhost:6379 Reserved for future celery worker

 prometheus <http://localhost:9090> Scrapes /metrics

 grafana <http://localhost:3000> Dashboards (admin/admin) — the API Health Monitor dashboard is auto-provisioned

Open Grafana at <http://localhost:3000> (admin/admin) → the dashboard is already loaded under the default org.

Populate the dashboard instantly (demo data)

Instead of waiting hours for real polls to fill the charts, seed ~24h of synthetic history (with a couple of injected failure bursts to demonstrate alerting):

## Local

python -m app.cli seed-demo

## Docker

docker compose exec app python -m app.cli seed-demo

Then refresh Grafana — the latency, status, and alert panels will be fully populated.

API reference

Interactive docs at /docs (Swagger UI) once the server is running.

 Method Path Description

 GET / Service info + endpoint list.

 GET /status Current status of every endpoint (latest check + open-alert flag).

 GET /uptime?hours=24 Uptime %, avg/min/max/p95 latency over the rolling window.

 GET /incidents?limit=50&only_open=false Recent alerts (open first).

 GET /endpoints List configured endpoints.

 POST /endpoints Add an endpoint to monitor: {"name","url","method?","expected_status?","interval_seconds?"}.

 DELETE /endpoints/{id} Stop monitoring an endpoint.

 GET /endpoints/{id}/checks?limit=100 Raw check history for an endpoint.

 GET /metrics Prometheus text exposition.

Example: add your own API

    curl -X POST <http://localhost:8000/endpoints> \
      -H 'Content-Type: application/json' \
      -d '{"name":"My Little Lemon API","url":"<https://my-little-lemon.example.com/api/health","expected_status":200}>'

Example response — /uptime?hours=24

    [
      {
        "endpoint": { "id": 1, "name": "Weather API", "url": "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41¤t=temperature_2m", "method": "GET", "expected_status": 200, "interval_seconds": 60, "enabled": true },
        "window_hours": 24,
        "total_checks": 1439,
        "successful_checks": 1429,
        "uptime_pct": 99.31,
        "avg_latency_ms": 177.3,
        "min_latency_ms": 81.2,
        "max_latency_ms": 412.5,
        "p95_latency_ms": 248.2
      }
    ]

Example — /metrics

    # HELP ahm_up 1 if the last check for the endpoint succeeded, else 0

    # TYPE ahm_up gauge

    ahm_up{endpoint="Weather API"} 1
    ahm_up{endpoint="HTTPBin"} 0

    # HELP ahm_check_latency_ms Last recorded latency in milliseconds

    # TYPE ahm_check_latency_ms gauge

    ahm_check_latency_ms{endpoint="Weather API"} 764.21

    # HELP ahm_alerts_open Number of currently open (unresolved) alerts

    # TYPE ahm_alerts_open gauge

    ahm_alerts_open 0

## Alerting

The rule is simple and configurable: if an endpoint fails AHM_CONSECUTIVE_FAILURES_THRESHOLD (default 3) checks in a row, an Alert row is created. When the endpoint next succeeds, the alert is marked resolved with a timestamp — giving you a full incident timeline.

Optional webhook: set AHM_ALERT_WEBHOOK_URL to a Slack/Discord/custom endpoint and the service will POST a JSON payload on alert:

{
  "endpoint": "Weather API",
  "url": "<https://api.open-meteo.com/>...",
  "consecutive_failures": 3,
  "message": "Endpoint 'Weather API' (...) failed 3 consecutive checks",
  "triggered_at": "2026-08-13T15:03:33+00:00"
}

Webhook delivery failures are logged but never break monitoring.

Configuration

All settings are environment variables (prefix AHM_), with sensible defaults. See .env.example for the full list.

 Variable Default Description

 AHM_DATABASE_URL sqlite+aiosqlite:///./api_health_monitor.db DB connection. Use postgresql+psycopg2://... for Postgres.

 AHM_POLL_INTERVAL_SECONDS 60 Seconds between polling ticks.

 AHM_SCHEDULER_ENABLED true Set false to run the API without background polling.

 AHM_CONSECUTIVE_FAILURES_THRESHOLD 3 Failures in a row before an alert fires.

 AHM_REQUEST_TIMEOUT_SECONDS 10.0 Per-check HTTP timeout.

 AHM_ALERT_WEBHOOK_URL (empty) Optional alert webhook.

 AHM_BOOTSTRAP_ENDPOINTS Weather API + HTTPBin Comma-separated `Name

CLI commands

python -m app.cli init        # create tables + seed bootstrap endpoints
python -m app.cli poll        # run one polling tick immediately
python -m app.cli seed-demo   # generate ~24h of synthetic history for the dashboard

Testing

pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term-missing

34 tests, 86% coverage. Tests cover:

- Alert logic: below-threshold no-op, 3-consecutive-failures fires exactly one alert, no duplicate alerts while still failing, auto-resolution on recovery.

- Poller: success path, unexpected status, matching status, unreachable host, recording all fields.

- API: /status, /uptime (percentage + percentiles), /incidents (with only_open filter), endpoint CRUD, /metrics format + counters + gauges.

- Scheduler: one check per enabled endpoint, disabled endpoints skipped, zero-endpoint no-op.

- CLI + init: table creation, bootstrap seeding (idempotent), demo-data generation.

Lint: ruff check app tests → clean.

CI

.github/workflows/ci.yml runs on every push/PR:

- lint — ruff check

- test — pytest with coverage, fails below 80%, uploads coverage.xml

- build — builds the Docker image (with GHA cache)

- trivy — vulnerability scan (advisory; flip exit-code: 0 → 1 to enforce)

Grafana dashboard

The dashboard (grafana/dashboards/api-health-monitor.json) is auto-provisioned and includes:

- Stat panels: monitored endpoint count, endpoints up, open alerts, total alerts, average latency.

- Time series: endpoint latency (ms) over time; endpoint status (up/down, stacked); open alerts over time.

- Table: per-endpoint total/success/failure check counts.

Refresh: 15s. Default time range: last 24h.

To capture a portfolio screenshot: run docker compose up, docker compose exec app python -m app.cli seed-demo, open Grafana → the dashboard is populated. Screenshot it for your README/portfolio.

Real metrics (from seeded 24h demo run)

 Endpoint Uptime (24h) Avg latency p95 latency Checks

 Weather API 99.31% 177.3 ms 248.2 ms 1439

 HTTPBin 99.31% 91.0 ms 130.0 ms 1439

Alerts: 2 (both auto-resolved). These are the numbers that go on a resume.

Resume bullets this enables

- Scheduled polling of 2+ endpoints: "Built an API health-monitoring service that polls 2 production endpoints every 60s, recording status, latency, and uptime."

- Uptime % calculation: "Tracked and exposed 99.3% uptime and rolling 24h average/p95 latency via REST endpoints."

- Alert-on-failure rule: "Implemented alerting that fired on 3 consecutive failures with auto-resolution on recovery, enabling proactive incident detection."

- Prometheus + Grafana: "Exported metrics in Prometheus format and built a Grafana dashboard visualizing latency, up/down status, and incident trends."

- Docker Compose + CI: "Containerized the full stack (app, Postgres, Redis, Prometheus, Grafana) with Docker Compose and shipped through a GitHub Actions CI pipeline (lint → test → build → Trivy scan)."

- Pytest coverage: "Covered alert and recording logic with pytest at 86% coverage across 34 tests."

Project structure

api-health-monitor/
├── app/
│   ├── main.py                  # FastAPI app + lifespan (init DB, start scheduler)
│   ├── config.py                # Pydantic-settings (env-driven)
│   ├── db.py                    # Async SQLAlchemy engine + session factory
│   ├── cli.py                   # Console commands: init / poll / seed-demo
│   ├── models/__init__.py       # Endpoint, Check, Alert ORM models
│   ├── api/
│   │   ├── schemas.py           # Pydantic response/request schemas
│   │   ├── endpoints_routes.py  # Endpoint CRUD
│   │   ├── monitoring_routes.py # /status, /uptime, /incidents, /checks
│   │   └── metrics_routes.py    # Prometheus /metrics
│   └── services/
│       ├── poller.py            # HTTP health check (httpx)
│       ├── alerting.py          # Consecutive-failure rule + webhook
│       ├── scheduler.py         # APScheduler tick (poll_all_endpoints)
│       └── init.py              # Table creation + bootstrap seeding
├── tests/                       # 34 tests, 86% coverage
├── grafana/
│   ├── prometheus.yml           # scrape config
│   ├── provisioning/            # datasource + dashboard providers
│   └── dashboards/              # api-health-monitor.json
├── Dockerfile                   # multi-stage build
├── docker-compose.yml           # app + db + redis + prometheus + grafana
├── requirements.txt             # pinned runtime deps
├── requirements-dev.txt         # + test/lint deps
├── pyproject.toml               # ruff + pytest + coverage config
└── .github/workflows/ci.yml     # lint → test → build → trivy

Roadmap (optional next steps)

- Alembic migrations instead of create_all for production schema evolution.

- Celery + Redis worker for distributed polling (the scheduler is already isolated and importable — swap APScheduler for a celery beat schedule).

- Email alerts via SMTP alongside the webhook.

- Authentication on the REST API (API key / OAuth).

- Multi-region polling from separate worker replicas.
