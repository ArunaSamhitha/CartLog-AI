import asyncio

from cartlog.memory import Memory, hashed_embedding
from cartlog.schemas import ProductQuery


def test_hashed_embedding_is_normalized_and_similar_for_overlap():
    a, b, c = (hashed_embedding(t) for t in ("sony wh-1000xm5 headphones", "sony headphones", "garden hose"))
    assert abs(float((a @ a)) - 1) < 1e-5
    assert a @ b > a @ c


def test_recall_finds_related_past_search(tmp_path):
    async def run():
        mem = Memory(str(tmp_path / "t.db"))
        q = ProductQuery(product="x")
        for text in ("sony noise cancelling headphones", "garden hose 50ft", "office chair"):
            await mem.remember("s1", text, q, [])
        await mem.remember("other-session", "sony headphones cheap", q, [])
        return await mem.recall("s1", "sony headphones under 200")

    recalled = asyncio.run(run())
    assert recalled and recalled[0] == "sony noise cancelling headphones"
    assert "sony headphones cheap" not in recalled  # other sessions stay private
