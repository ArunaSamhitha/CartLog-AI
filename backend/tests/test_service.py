import asyncio

from cartlog.memory import Memory
from cartlog.orchestrator import Orchestrator
from cartlog.service import SearchService


def test_text_search_end_to_end(tmp_path):
    async def run():
        async with Orchestrator() as orch:
            svc = SearchService(orch, Memory(str(tmp_path / "t.db")))
            first = await svc.search_text("used sony headphones under $200")
            second = await svc.search_text("sony headphones", first.session_id)
            return first, second

    first, second = asyncio.run(run())
    assert first.mock_mode and first.listings
    assert first.query.max_price == 200 and first.query.condition == "used"
    assert all(l.price <= 200 for l in first.listings)
    assert first.listings == sorted(first.listings, key=lambda l: (-l.score, l.price))
    assert second.remembered == ["used sony headphones under $200"]
