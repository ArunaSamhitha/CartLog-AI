"""MCP server exposing Amazon product search through the Rainforest API.

Needs RAINFOREST_API_KEY. Without it, returns deterministic mock listings.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import filter_price, mock_enabled, mock_listings, simulate_latency  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer("amazon", instructions="Search Amazon.com products by keyword and budget.")

SEARCH_URL = "https://api.rainforestapi.com/request"


@server.tool()
async def search_amazon(query: str, max_price: float | None = None, limit: int = 8) -> dict:
    """Search Amazon.com for products matching `query`, optionally under `max_price` USD."""
    if mock_enabled("RAINFOREST_API_KEY"):
        await simulate_latency("amazon")
        return {"listings": mock_listings("amazon", query, max_price, limit), "mock": True}

    import httpx

    params = {"api_key": os.environ["RAINFOREST_API_KEY"], "type": "search",
              "amazon_domain": "amazon.com", "search_term": query}
    if max_price is not None:
        params["max_price"] = str(max_price)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        results = resp.json().get("search_results", [])

    listings = []
    for item in results:
        price = (item.get("price") or (item.get("prices") or [{}])[0]) or {}
        if price.get("value") is None:
            continue
        listings.append({
            "marketplace": "amazon",
            "title": item.get("title", ""),
            "price": float(price["value"]),
            "currency": price.get("currency", "USD"),
            "url": item.get("link", ""),
            "image_url": item.get("image"),
            "condition": "New",
            "rating": item.get("rating"),
        })
    return {"listings": filter_price(listings, max_price)[:limit], "mock": False}


if __name__ == "__main__":
    server.run("stdio")
