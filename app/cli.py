"""Console entry points (the Django "management command" equivalent).

Usage:
  python -m app.cli poll          # run one polling tick against all endpoints
  python -m app.cli seed-demo     # generate ~24h of synthetic check history
  python -m app.cli init          # create tables + seed bootstrap endpoints
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from .db import AsyncSessionLocal, engine
from .models import Alert, Base, Check, Endpoint
from .services.init import init_db, seed_bootstrap_endpoints
from .services.scheduler import poll_all_endpoints


async def cmd_init() -> None:
    await init_db()
    await seed_bootstrap_endpoints()
    print("Database initialized and bootstrap endpoints seeded.")


async def cmd_poll() -> None:
    await init_db()
    await seed_bootstrap_endpoints()
    await poll_all_endpoints()
    print("Polling tick complete.")


async def cmd_seed_demo() -> None:
    """Generate ~24h of synthetic check history for all endpoints.

    Useful so the Grafana dashboard has data to display without waiting
    hours for real polls. Mixes in a few failures to demonstrate alerting.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_bootstrap_endpoints()

    async with AsyncSessionLocal() as session:
        endpoints = list((await session.execute(select(Endpoint))).scalars().all())
        if not endpoints:
            print("No endpoints configured.")
            return

        now = datetime.now(UTC)
        # 24h of 1-minute checks = 1440 per endpoint.
        checks_per_endpoint = 1440
        inserted = 0
        for ep in endpoints:
            base_latency = random.uniform(80, 250)
            # Inject 2 failure bursts of ~5 each to trigger alerts.
            burst_starts = random.sample(
                range(50, checks_per_endpoint - 50), 2
            )
            failure_indices = set()
            for bs in burst_starts:
                for i in range(bs, bs + 5):
                    failure_indices.add(i)

            for i in range(checks_per_endpoint):
                ts = now - timedelta(minutes=(checks_per_endpoint - i))
                failed = i in failure_indices
                if failed:
                    latency = random.uniform(500, 5000)
                    success = False
                    status_code = random.choice([500, 502, 503, None])
                    error = "Simulated failure"
                else:
                    latency = max(10.0, random.gauss(base_latency, base_latency * 0.25))
                    success = True
                    status_code = ep.expected_status
                    error = None
                session.add(
                    Check(
                        endpoint_id=ep.id,
                        timestamp=ts,
                        status_code=status_code,
                        latency_ms=round(latency, 2),
                        success=success,
                        error=error,
                    )
                )
                inserted += 1
                if inserted % 500 == 0:
                    await session.commit()

            # Add a resolved alert for the first burst.
            session.add(
                Alert(
                    endpoint_id=ep.id,
                    triggered_at=now - timedelta(minutes=checks_per_endpoint - burst_starts[0]),
                    resolved_at=now - timedelta(minutes=checks_per_endpoint - burst_starts[0] - 10),
                    resolved=True,
                    consecutive_failures=5,
                    message=f"Endpoint '{ep.name}' failed 5 consecutive checks (simulated)",
                    webhook_sent=False,
                )
            )
        await session.commit()
    print(f"Seeded {inserted} synthetic checks across {len(endpoints)} endpoint(s).")


COMMANDS = {
    "init": cmd_init,
    "poll": cmd_poll,
    "seed-demo": cmd_seed_demo,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="api-health-monitor", description=__doc__)
    parser.add_argument("command", choices=list(COMMANDS), help="Command to run")
    args = parser.parse_args(argv)
    asyncio.run(COMMANDS[args.command]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
