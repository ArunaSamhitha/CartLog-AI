"""The search pipeline, independent of the web framework.

understand (text or image) -> fan out to agents over MCP -> rank -> remember
"""
import asyncio
import time
import uuid

from .config import settings
from .memory import Memory
from .orchestrator import Orchestrator
from .ranking import rank
from .schemas import ProductQuery, Research, SearchResponse
from .understanding import parse_image, parse_text


class SearchService:
    def __init__(self, orchestrator: Orchestrator, memory: Memory):
        self.orchestrator = orchestrator
        self.memory = memory

    async def search_text(self, text: str, session_id: str | None = None) -> SearchResponse:
        t0 = time.perf_counter()
        query = await parse_text(text)
        return await self._search(query, text, session_id, t0)

    async def search_image(self, image: bytes, mime: str, note: str | None = None,
                           session_id: str | None = None) -> SearchResponse:
        t0 = time.perf_counter()
        query = await parse_image(image, mime, note)
        label = f"[photo] {query.search_string()}" + (f" ({note})" if note else "")
        return await self._search(query, label, session_id, t0)

    async def _search(self, query: ProductQuery, text: str, session_id: str | None, t0: float) -> SearchResponse:
        session_id = session_id or uuid.uuid4().hex
        parse_ms = round((time.perf_counter() - t0) * 1000, 1)

        # Memory lookup runs alongside the agents, so it adds no wait.
        (results, timings), remembered = await asyncio.gather(
            self.orchestrator.run(query),
            self.memory.recall(session_id, text),
        )
        research = Research.model_validate(results["research"]) if "research" in results else None
        listings = rank(results, query, research)
        mock = settings.force_mock or any(r.get("mock") for r in results.values())

        response = SearchResponse(
            session_id=session_id, query=query, listings=listings, research=research,
            timings=timings, parse_ms=parse_ms, total_ms=round((time.perf_counter() - t0) * 1000, 1),
            mock_mode=mock, remembered=remembered,
        )
        await self.memory.remember(session_id, text, query, listings)
        return response
