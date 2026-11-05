"""Merge listings from all marketplaces into one ranked list."""
import re

from .schemas import Listing, ProductQuery, Research


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_listing(listing: Listing, query: ProductQuery, research: Research | None) -> float:
    """0-1 score: mostly title relevance, then value for money, then rating.

    Value for money compares the price with the typical range found by the
    research agent (or with the user's budget when research is unavailable).
    """
    wanted = _tokens(query.search_string())
    relevance = len(wanted & _tokens(listing.title)) / len(wanted) if wanted else 0.0

    reference = None
    if research and research.typical_price_range:
        low, high = research.typical_price_range
        reference = (low + high) / 2
    elif query.max_price:
        reference = query.max_price
    value = 0.5
    if reference:
        # At the reference price -> 0.5; free -> 1.0; double the reference -> 0.0
        value = max(0.0, min(1.0, 0.5 - (listing.price - reference) / (2 * reference)))

    rating = (listing.rating - 3.0) / 2.0 if listing.rating else 0.5
    if query.condition != "any" and listing.condition and query.condition not in listing.condition.lower():
        relevance *= 0.7
    return round(0.6 * relevance + 0.3 * value + 0.1 * max(0.0, min(1.0, rating)), 4)


def rank(results: dict[str, dict], query: ProductQuery, research: Research | None, limit: int = 12) -> list[Listing]:
    listings: list[Listing] = []
    seen: set[tuple[str, str, float]] = set()
    for agent in ("ebay", "amazon"):
        for raw in (results.get(agent) or {}).get("listings", []):
            listing = Listing.model_validate(raw)
            key = (listing.marketplace, listing.title.lower(), listing.price)
            if key in seen:
                continue
            seen.add(key)
            listing.score = score_listing(listing, query, research)
            listings.append(listing)
    listings.sort(key=lambda l: (-l.score, l.price))
    return listings[:limit]
