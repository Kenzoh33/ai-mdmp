"""Steady demo traffic for the sentiment model, through the ingress.

    python loadgen/traffic.py --rate 5            # until Ctrl-C
    python loadgen/traffic.py --rate 10 --duration 60

Open loop: one request is started every 1/rate seconds whether or not earlier ones have
answered, so a slow canary cannot quietly lower the offered rate. When --concurrency requests
are already in flight, the tick is counted as dropped instead of queueing without bound.
"""

import argparse
import asyncio
import json
import math
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TextIO

import httpx

DEFAULT_URL = "http://localhost/models/sentiment/predict"

# A mix of clear and ambiguous reviews so prediction confidence varies.
REVIEWS = [
    "a wonderful, moving film with brilliant performances",
    "one of the best movies of the year, funny and warm",
    "a beautiful story told with real heart",
    "sharp writing and a cast that clearly loves the material",
    "an absolute joy from start to finish",
    "gorgeous to look at and genuinely touching",
    "the kind of movie that reminds you why you love cinema",
    "clever, fast and surprisingly emotional",
    "a confident debut that never puts a foot wrong",
    "i laughed, i cried, i want to see it again",
    "a boring, tedious mess that goes nowhere",
    "terrible acting and a plot full of holes",
    "the worst film i have seen in years",
    "lifeless, predictable and far too long",
    "a dull, forgettable disappointment",
    "painfully unfunny and badly edited",
    "nothing happens for two hours and then it just ends",
    "a waste of a talented cast",
    "cheap, loud and completely empty",
    "i checked my watch every ten minutes",
    "it has its moments but never quite comes together",
    "not bad, not great, just fine",
    "the first half drags but the ending is strong",
    "good performances stuck in a messy script",
    "fans will enjoy it, everyone else may be bored",
    "a decent rental for a rainy afternoon",
    "ambitious and uneven, sometimes brilliant, sometimes silly",
    "pretty to look at, thin on story",
    "better than the trailer suggested, worse than the book",
    "a solid if unremarkable sequel",
]


@dataclass
class Stats:
    sent: int = 0
    ok: int = 0
    dropped: int = 0
    errors: Counter = field(default_factory=Counter)
    latencies: list[float] = field(default_factory=list)

    def summary(self) -> dict:
        lat = self.latencies
        return {
            "sent": self.sent,
            "ok": self.ok,
            "errors": dict(self.errors),
            "dropped": self.dropped,
            "mean_latency_s": round(sum(lat) / len(lat), 4) if lat else None,
            "p95_latency_s": round(p95(lat), 4) if lat else None,
        }


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def log(out: TextIO, message: str, **fields: object) -> None:
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": "INFO",
        "service": "loadgen",
        "message": message,
        **fields,
    }
    print(json.dumps(entry), file=out, flush=True)


async def send_one(
    client: httpx.AsyncClient, url: str, text: str, timeout: float, stats: Stats
) -> None:
    start = time.perf_counter()
    try:
        response = await client.post(url, json={"text": text}, timeout=timeout)
    except httpx.TimeoutException:
        stats.errors["timeout"] += 1
        return
    except httpx.HTTPError:
        stats.errors["connection_error"] += 1
        return
    stats.latencies.append(time.perf_counter() - start)
    if response.is_success:
        stats.ok += 1
    else:
        stats.errors[str(response.status_code)] += 1


async def run(
    client: httpx.AsyncClient,
    url: str,
    rate: float,
    duration: float,
    stats: Stats,
    *,
    concurrency: int = 20,
    timeout: float = 5.0,
    report_every: float = 10.0,
    rng: random.Random | None = None,
    out: TextIO = sys.stdout,
) -> Stats:
    """Send rate requests per second for duration seconds (0 = forever)."""
    rng = rng or random.Random()
    loop = asyncio.get_running_loop()
    interval = 1.0 / rate
    start = loop.time()
    # Tick i fires at start + i * interval: computed, not summed, so float error can't add ticks.
    ticks = round(rate * duration) if duration > 0 else math.inf
    tick = 0
    next_report = start + report_every
    in_flight: set[asyncio.Task] = set()

    while tick < ticks:
        if len(in_flight) >= concurrency:
            stats.dropped += 1
        else:
            stats.sent += 1
            task = asyncio.create_task(send_one(client, url, rng.choice(REVIEWS), timeout, stats))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
        if loop.time() >= next_report:
            log(out, "progress", **stats.summary())
            next_report += report_every
        tick += 1
        await asyncio.sleep(max(0.0, start + tick * interval - loop.time()))

    if in_flight:
        await asyncio.gather(*in_flight)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Steady demo traffic for the sentiment model.")
    parser.add_argument("--url", default=os.getenv("LOADGEN_URL", DEFAULT_URL))
    parser.add_argument(
        "--rate", type=float, default=float(os.getenv("LOADGEN_RATE", "5")), help="requests/s"
    )
    parser.add_argument("--duration", type=float, default=0, help="seconds, 0 = until Ctrl-C")
    parser.add_argument("--concurrency", type=int, default=20, help="max requests in flight")
    parser.add_argument("--timeout", type=float, default=5.0, help="per-request timeout (s)")
    args = parser.parse_args()
    if args.rate <= 0:
        parser.error("--rate must be positive")

    stats = Stats()
    log(sys.stdout, "starting", url=args.url, rate=args.rate, duration=args.duration)

    async def _go() -> None:
        async with httpx.AsyncClient() as client:
            await run(
                client,
                args.url,
                args.rate,
                args.duration,
                stats,
                concurrency=args.concurrency,
                timeout=args.timeout,
            )

    try:
        asyncio.run(_go())
    except KeyboardInterrupt:
        pass
    log(sys.stdout, "finished", **stats.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
