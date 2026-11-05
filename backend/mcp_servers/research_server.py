"""MCP server that researches a product on the web through the Serper (Google Search) API.

Returns a short summary from the top results and the typical price range found
in their snippets. Needs SERPER_API_KEY; mock data otherwise.
"""
import os
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import _rng, mock_enabled, simulate_latency  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer("research", instructions="Research a product: reviews, typical price, what to watch for.")

SEARCH_URL = "https://google.serper.dev/search"
PRICE_RE = re.compile(r"\$\s?(\d{1,5}(?:,\d{3})*(?:\.\d{2})?)")


def price_range(texts: list[str]) -> list[float] | None:
    """Interquartile price range of every $ amount mentioned in the snippets."""
    prices = sorted(float(m.replace(",", "")) for t in texts for m in PRICE_RE.findall(t))
    prices = [p for p in prices if p >= 1]
    if len(prices) < 2:
        return None
    if len(prices) < 4:
        return [prices[0], prices[-1]]
    q1, _, q3 = statistics.quantiles(prices, n=4)
    return [round(q1, 2), round(q3, 2)]


@server.tool()
async def research_product(query: str) -> dict:
    """Look up reviews and pricing for a product. Returns summary, price range and sources."""
    if mock_enabled("SERPER_API_KEY"):
        await simulate_latency("research")
        rng = _rng("research", query.lower())
        low = round(rng.uniform(30, 250), 2)
        return {
            "summary": f"Reviewers generally rate the {query} well for the price. Common notes: check the "
                       f"seller's return policy on used units and compare battery or warranty terms.",
            "typical_price_range": [low, round(low * rng.uniform(1.3, 1.8), 2)],
            "sources": [],
            "mock": True,
        }

    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(SEARCH_URL, headers={"X-API-KEY": os.environ["SERPER_API_KEY"]},
                                 json={"q": f"{query} review price", "num": 8})
        resp.raise_for_status()
        organic = resp.json().get("organic", [])

    snippets = [r.get("snippet", "") for r in organic]
    summary = " ".join(s for s in snippets[:3] if s) or f"No reviews found for {query}."
    return {
        "summary": summary,
        "typical_price_range": price_range([r.get("title", "") + " " + r.get("snippet", "") for r in organic]),
        "sources": [r["link"] for r in organic[:3] if r.get("link")],
        "mock": False,
    }


if __name__ == "__main__":
    server.run("stdio")
