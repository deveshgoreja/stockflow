import socket
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import httpx
import pytest
import uvicorn

from app.database.connection import SessionLocal
from app.main import app
from tests.helpers import assert_inventory_matches_movements

T = TypeVar("T")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(migrated_database: None) -> Iterator[str]:
    """A real Uvicorn server, so concurrent requests hit the full HTTP + DB stack."""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", backlog=512)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Uvicorn did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def _clean_and_check_invariant(clean_database: None) -> Iterator[None]:
    """Start empty; after every concurrency test, the stock ledger must still balance."""
    yield
    with SessionLocal() as session:
        assert_inventory_matches_movements(session)


@pytest.fixture
def api(live_server: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=live_server, timeout=60) as client:
        yield client


@pytest.fixture
def run_concurrently(live_server: str) -> Callable[..., list]:
    """Run fn(client, i) in `count` threads that are released at the same instant.

    Each thread has its own HTTP client (own TCP connection); the server gives
    each request its own DB session, so the database sees genuinely parallel
    transactions.
    """

    def run(count: int, fn: Callable[[httpx.Client, int], T]) -> list[T]:
        barrier = threading.Barrier(count)

        def worker(index: int) -> T:
            with httpx.Client(base_url=live_server, timeout=120) as client:
                barrier.wait()
                return fn(client, index)

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(worker, range(count)))

    return run
