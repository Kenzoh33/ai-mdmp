import asyncio
import io
import json
import random

import httpx
from traffic import REVIEWS, Stats, p95, run


def collect(handler) -> tuple[Stats, list[dict], io.StringIO]:
    """Run 0.2 s at 50 req/s (10 requests) against a mock transport."""
    bodies: list[dict] = []

    def recording(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return handler(request)

    async def go() -> Stats:
        transport = httpx.MockTransport(recording)
        async with httpx.AsyncClient(transport=transport) as client:
            return await run(
                client,
                "http://test/models/sentiment/predict",
                rate=50,
                duration=0.2,
                stats=Stats(),
                rng=random.Random(0),
                out=out,
            )

    out = io.StringIO()
    return asyncio.run(go()), bodies, out


def test_sends_rate_times_duration_requests() -> None:
    stats, bodies, _ = collect(lambda r: httpx.Response(200, json={"label": "positive"}))

    assert stats.sent == 10
    assert stats.ok == 10
    assert not stats.errors
    assert len(stats.latencies) == 10
    assert all(set(body) == {"text"} and body["text"] in REVIEWS for body in bodies)


def test_http_errors_are_counted_by_status() -> None:
    stats, _, _ = collect(lambda r: httpx.Response(500, json={"error": {}}))
    assert stats.ok == 0
    assert stats.errors == {"500": 10}


def test_timeouts_and_connection_errors_are_counted() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] % 2:
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("refused", request=request)

    stats, _, _ = collect(flaky)
    assert stats.errors == {"timeout": 5, "connection_error": 5}
    assert stats.latencies == []


def test_full_concurrency_drops_ticks_instead_of_queueing() -> None:
    async def go() -> Stats:
        async def slow(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1)
            return httpx.Response(200)

        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
            return await run(
                client, "http://test/", rate=50, duration=0.2, stats=Stats(), concurrency=2
            )

    stats = asyncio.run(go())
    assert stats.sent == 2
    assert stats.dropped == 8


def test_p95_and_summary() -> None:
    assert p95([float(i) for i in range(1, 101)]) == 95.0
    assert p95([0.3]) == 0.3
    assert Stats().summary()["p95_latency_s"] is None
