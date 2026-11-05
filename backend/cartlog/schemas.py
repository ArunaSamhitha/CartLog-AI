"""Data shapes shared by the API, the agents and the frontend."""
from typing import Literal

from pydantic import BaseModel, Field

Marketplace = Literal["ebay", "amazon"]


class ProductQuery(BaseModel):
    """A structured search, extracted from free text or from a photo."""

    product: str = Field(description="What the item is, e.g. 'noise-cancelling headphones'")
    brand: str | None = None
    model: str | None = None
    attributes: list[str] = Field(default_factory=list, description="Color, size, capacity, condition...")
    max_price: float | None = Field(default=None, description="Upper budget in USD")
    condition: Literal["new", "used", "any"] = "any"

    def search_string(self) -> str:
        parts = [self.brand, self.model, self.product, *self.attributes]
        seen, words = set(), []
        for part in parts:
            if part and part.lower() not in seen:
                seen.add(part.lower())
                words.append(part)
        return " ".join(words)


class Listing(BaseModel):
    marketplace: Marketplace
    title: str
    price: float
    currency: str = "USD"
    url: str
    image_url: str | None = None
    condition: str | None = None
    rating: float | None = None
    score: float = 0.0  # filled in by ranking


class Research(BaseModel):
    summary: str
    typical_price_range: tuple[float, float] | None = None
    sources: list[str] = Field(default_factory=list)


class AgentTiming(BaseModel):
    agent: str
    ms: float
    ok: bool
    error: str | None = None


class SearchResponse(BaseModel):
    session_id: str
    query: ProductQuery
    listings: list[Listing]
    research: Research | None
    timings: list[AgentTiming]
    parse_ms: float
    total_ms: float
    mock_mode: bool
    remembered: list[str] = Field(default_factory=list, description="Related past searches pulled from memory")


class TextSearchRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    session_id: str | None = None
