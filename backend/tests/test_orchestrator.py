import asyncio
import os

from cartlog.orchestrator import AGENTS, Orchestrator
from cartlog.schemas import ProductQuery

QUERY = ProductQuery(product="mechanical keyboard", max_price=150)


def test_all_agents_answer_over_mcp():
    async def run():
        async with Orchestrator() as orch:
            return await orch.run(QUERY)

    results, timings = asyncio.run(run())
    assert set(results) == {"research", "ebay", "amazon"}
    assert all(t.ok for t in timings)
    assert all(l["price"] <= 150 for l in results["ebay"]["listings"] + results["amazon"]["listings"])


def test_parallel_is_faster_than_sequential():
    async def run():
        async with Orchestrator() as orch:
            await orch.run(QUERY)  # warm up
            t0 = asyncio.get_running_loop().time(); await orch.run(QUERY, parallel=True)
            par = asyncio.get_running_loop().time() - t0
            t0 = asyncio.get_running_loop().time(); await orch.run(QUERY, parallel=False)
            seq = asyncio.get_running_loop().time() - t0
            return par, seq

    par, seq = asyncio.run(run())
    assert par < seq * 0.7


def test_servers_receive_environment():
    """API keys and settings must reach the agent processes."""
    os.environ["MOCK_LATENCY_EBAY_MS"] = "0"
    os.environ["MOCK_LATENCY_RESEARCH_MS"] = "0"
    os.environ["MOCK_LATENCY_AMAZON_MS"] = "3000"
    try:
        async def run():
            async with Orchestrator() as orch:
                return await orch.run(QUERY)

        _, timings = asyncio.run(run())
    finally:
        for k in ("EBAY", "RESEARCH", "AMAZON"):
            del os.environ[f"MOCK_LATENCY_{k}_MS"]
    by_agent = {t.agent: t.ms for t in timings}
    assert by_agent["ebay"] < 300 and by_agent["amazon"] > 400  # 3000 ms x 0.2 scale = ~600 ms


def test_slow_agent_times_out_without_failing_search():
    os.environ["MOCK_LATENCY_AMAZON_MS"] = "20000"
    try:
        async def run():
            async with Orchestrator(timeout_s=1.0) as orch:
                return await orch.run(QUERY)

        results, timings = asyncio.run(run())
    finally:
        del os.environ["MOCK_LATENCY_AMAZON_MS"]
    by_agent = {t.agent: t for t in timings}
    assert not by_agent["amazon"].ok and "timed out" in by_agent["amazon"].error
    assert "ebay" in results and "research" in results
