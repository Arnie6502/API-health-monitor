"""Test configuration: isolated in-memory SQLite per test + shared fixtures."""
import os
import sys
from pathlib import Path

# Ensure the project root is importable as `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force SQLite in-memory for tests and disable the scheduler.
os.environ.setdefault("AHM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AHM_SCHEDULER_ENABLED", "false")
os.environ.setdefault("AHM_POLL_INTERVAL_SECONDS", "60")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db import AsyncSessionLocal, Base, engine  # noqa: E402
from app.main import create_app  # noqa: E402


def _make_server(status_code: int):
    """Build a background HTTP server on a free port returning `status_code`.

    Returns (server, url). Use server.shutdown() to stop.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(status_code)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):  # silence
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}/", thread


@pytest_asyncio.fixture
async def mock_200_server():
    server, url, _ = _make_server(200)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@pytest_asyncio.fixture
async def mock_404_server():
    server, url, _ = _make_server(404)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@pytest_asyncio.fixture
async def setup_db():
    """Create a fresh in-memory schema for each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session(setup_db):
    async with AsyncSessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client(setup_db):
    """ASGI test client (no real network socket)."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
