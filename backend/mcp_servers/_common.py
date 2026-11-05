"""Helpers shared by the three MCP servers: mock data and price filtering."""
import asyncio
import hashlib
import os
import random
import urllib.parse


def mock_enabled(*required_keys: str) -> bool:
    if os.getenv("CARTLOG_MOCK", "").lower() in {"1", "true", "yes"}:
        return True
    return not all(os.getenv(k) for k in required_keys)


async def simulate_latency(agent: str) -> None:
    """Mock agents sleep for a realistic API round trip so timings mean something.

    Defaults are in the range real marketplace APIs answer in. Override with
    e.g. MOCK_LATENCY_EBAY_MS=500, or set MOCK_LATENCY_SCALE=0 in tests.
    """
    defaults = {"research": 700, "ebay": 900, "amazon": 1100}
    base = float(os.getenv(f"MOCK_LATENCY_{agent.upper()}_MS", defaults[agent]))
    scale = float(os.getenv("MOCK_LATENCY_SCALE", "1"))
    await asyncio.sleep(max(0.0, base * random.uniform(0.85, 1.15) * scale / 1000))


def _rng(*parts: str) -> random.Random:
    seed = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def mock_listings(marketplace: str, query: str, max_price: float | None, limit: int) -> list[dict]:
    """Deterministic fake listings for a query, so demos and tests are repeatable."""
    rng = _rng(marketplace, query.lower())
    base = rng.uniform(25, 400)
    variants = ["", "(Renewed)", "- Latest Model", "Bundle with Case", "Open Box", "- 2-Pack", "Refurbished", "Like New"]
    search_url = {
        "ebay": "https://www.ebay.com/sch/i.html?_nkw=",
        "amazon": "https://www.amazon.com/s?k=",
    }[marketplace] + urllib.parse.quote_plus(query)
    out = []
    for i in range(limit + 4):
        price = round(base * rng.uniform(0.6, 1.4), 2)
        variant = variants[i % len(variants)]
        condition = "Used" if variant in {"(Renewed)", "Open Box", "Refurbished", "Like New"} else "New"
        out.append({
            "marketplace": marketplace,
            "title": f"{query.title()} {variant}".strip(),
            "price": price,
            "currency": "USD",
            "url": search_url,
            "image_url": None,
            "condition": condition,
            "rating": round(rng.uniform(3.6, 4.9), 1) if marketplace == "amazon" else None,
        })
    return filter_price(out, max_price)[:limit]


def filter_price(listings: list[dict], max_price: float | None) -> list[dict]:
    if max_price is None:
        return listings
    return [item for item in listings if item["price"] <= max_price]
