"""Measure end-to-end agent latency: parallel fan-out vs calling agents one by one.

    python benchmark.py --runs 20

Uses live APIs for any agent whose keys are set, and mock agents (with
simulated network latency) for the rest. The output says which.
"""
import argparse
import asyncio
import os
import statistics
import time

from cartlog.orchestrator import Orchestrator
from cartlog.schemas import ProductQuery

QUERIES = [
    ProductQuery(product="noise cancelling headphones", brand="Sony", max_price=300),
    ProductQuery(product="mechanical keyboard", attributes=["hot-swappable"], max_price=150),
    ProductQuery(product="running shoes", brand="Nike", attributes=["size 9"]),
    ProductQuery(product="standing desk", max_price=400, condition="used"),
]


def pct(values, q):
    return statistics.quantiles(values, n=100)[q - 1] if len(values) >= 2 else values[0]


async def main(runs: int):
    async with Orchestrator() as orch:
        await orch.run(QUERIES[0])  # warm-up: first call pays connection setup
        results = {"parallel": [], "sequential": []}
        modes = set()
        for i in range(runs):
            q = QUERIES[i % len(QUERIES)]
            for mode in ("parallel", "sequential"):
                t0 = time.perf_counter()
                data, _ = await orch.run(q, parallel=mode == "parallel")
                results[mode].append((time.perf_counter() - t0) * 1000)
                modes |= {"mock" if d.get("mock") else "live" for d in data.values()}

    print(f"Agents: {', '.join(sorted(modes))} | runs: {runs} | queries: {len(QUERIES)}")
    if "mock" in modes:
        print("Note: mock agents sleep for a simulated API round trip "
              f"(scale={os.getenv('MOCK_LATENCY_SCALE', '1')}); these numbers show the orchestration effect, not real API speed.")
    for mode, values in results.items():
        print(f"{mode:>10}: median {statistics.median(values):7.1f} ms | p95 {pct(values, 95):7.1f} ms")
    par, seq = statistics.median(results["parallel"]), statistics.median(results["sequential"])
    print(f"Parallel fan-out cuts median latency by {100 * (1 - par / seq):.0f}%")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=20)
    asyncio.run(main(p.parse_args().runs))
