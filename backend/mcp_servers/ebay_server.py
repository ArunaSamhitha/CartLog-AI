"""MCP server exposing eBay search through the eBay Browse API.

Needs EBAY_CLIENT_ID and EBAY_CLIENT_SECRET (a free eBay developer account).
Without them it returns deterministic mock listings.
"""
import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import filter_price, mock_enabled, mock_listings, simulate_latency  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402

server = MCPServer("ebay", instructions="Search eBay listings by keyword and budget.")

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_token: dict = {"value": None, "expires": 0.0}


async def _get_token(client) -> str:
    """OAuth client-credentials token, cached until shortly before it expires."""
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    creds = f"{os.environ['EBAY_CLIENT_ID']}:{os.environ['EBAY_CLIENT_SECRET']}"
    resp = await client.post(
        TOKEN_URL,
        headers={"Authorization": "Basic " + base64.b64encode(creds.encode()).decode(),
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
    )
    resp.raise_for_status()
    body = resp.json()
    _token.update(value=body["access_token"], expires=time.time() + body.get("expires_in", 7200))
    return _token["value"]


@server.tool()
async def search_ebay(query: str, max_price: float | None = None, condition: str = "any", limit: int = 8) -> dict:
    """Search eBay for listings matching `query`, optionally under `max_price` USD."""
    if mock_enabled("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"):
        await simulate_latency("ebay")
        return {"listings": mock_listings("ebay", query, max_price, limit), "mock": True}

    import httpx

    filters = []
    if max_price is not None:
        filters.append(f"price:[..{max_price}],priceCurrency:USD")
    if condition == "new":
        filters.append("conditions:{NEW}")
    elif condition == "used":
        filters.append("conditions:{USED}")
    params = {"q": query, "limit": str(limit)}
    if filters:
        params["filter"] = ",".join(filters)

    async with httpx.AsyncClient(timeout=10) as client:
        token = await _get_token(client)
        resp = await client.get(SEARCH_URL, params=params, headers={
            "Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
        resp.raise_for_status()
        items = resp.json().get("itemSummaries", [])

    listings = []
    for item in items:
        price = item.get("price", {})
        try:
            value = float(price.get("value"))
        except (TypeError, ValueError):
            continue
        listings.append({
            "marketplace": "ebay",
            "title": item.get("title", ""),
            "price": value,
            "currency": price.get("currency", "USD"),
            "url": item.get("itemWebUrl", ""),
            "image_url": (item.get("image") or {}).get("imageUrl"),
            "condition": item.get("condition"),
            "rating": None,
        })
    return {"listings": filter_price(listings, max_price), "mock": False}


if __name__ == "__main__":
    server.run("stdio")
