"""Search history (SQLite) plus semantic memory of past searches (vector search).

Every search is stored in SQLite. Its text is also embedded and stored as a
vector, so a new search can pull up related earlier ones ("you looked at Sony
headphones under $200 last week").

Vectors go to Pinecone when PINECONE_API_KEY is set. Otherwise they live in the
same SQLite file and are searched with NumPy cosine similarity, which is plenty
for one user's history.
"""
import hashlib
import json
import re
import sqlite3
import time

import numpy as np

from .config import settings
from .schemas import Listing, ProductQuery

LOCAL_DIM = 256

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    text TEXT NOT NULL,
    query_json TEXT NOT NULL,
    top_listings_json TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_searches_session ON searches(session_id, created_at);
"""


def hashed_embedding(text: str, dim: int = LOCAL_DIM) -> np.ndarray:
    """Keyless fallback embedding: hashed word and character-trigram counts, L2-normalized.

    Much weaker than a learned embedding, but it captures word overlap, which is
    enough to group "sony wh-1000xm5" with "sony headphones".
    """
    vec = np.zeros(dim, dtype=np.float32)
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = words + [w[i:i + 3] for w in words for i in range(max(1, len(w) - 2))]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


class Memory:
    def __init__(self, db_path: str | None = None):
        self.db = sqlite3.connect(db_path or settings.db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self._pinecone = None
        if settings.pinecone_api_key and settings.llm_enabled:
            from pinecone import Pinecone

            self._pinecone = Pinecone(api_key=settings.pinecone_api_key).Index(settings.pinecone_index)

    async def embed(self, text: str) -> np.ndarray:
        if settings.llm_enabled:
            from openai import AsyncOpenAI

            resp = await AsyncOpenAI(api_key=settings.openai_api_key).embeddings.create(
                model=settings.embedding_model, input=text)
            return np.asarray(resp.data[0].embedding, dtype=np.float32)
        return hashed_embedding(text)

    async def remember(self, session_id: str, text: str, query: ProductQuery, listings: list[Listing]) -> None:
        vec = await self.embed(text)
        top = [l.model_dump(include={"marketplace", "title", "price", "url"}) for l in listings[:3]]
        cur = self.db.execute(
            "INSERT INTO searches (session_id, created_at, text, query_json, top_listings_json, embedding) VALUES (?,?,?,?,?,?)",
            (session_id, time.time(), text, query.model_dump_json(), json.dumps(top),
             None if self._pinecone else vec.tobytes()),
        )
        self.db.commit()
        if self._pinecone:
            self._pinecone.upsert(vectors=[{"id": str(cur.lastrowid), "values": vec.tolist(),
                                            "metadata": {"session_id": session_id, "text": text}}])

    async def recall(self, session_id: str, text: str, k: int = 3, min_score: float = 0.45) -> list[str]:
        """Past searches in this session most similar to `text`."""
        vec = await self.embed(text)
        if self._pinecone:
            res = self._pinecone.query(vector=vec.tolist(), top_k=k + 1, include_metadata=True,
                                       filter={"session_id": {"$eq": session_id}})
            hits = [(m.score, m.metadata["text"]) for m in res.matches]
        else:
            rows = self.db.execute(
                "SELECT text, embedding FROM searches WHERE session_id=? AND embedding IS NOT NULL ORDER BY created_at DESC LIMIT 500",
                (session_id,)).fetchall()
            if not rows:
                return []
            matrix = np.stack([np.frombuffer(blob, dtype=np.float32) for _, blob in rows])
            scores = matrix @ vec
            hits = [(float(scores[i]), rows[i][0]) for i in np.argsort(-scores)[: k + 1]]
        out = []
        for score, past in hits:
            if score >= min_score and past.strip().lower() != text.strip().lower() and past not in out:
                out.append(past)
        return out[:k]

    def history(self, session_id: str, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT created_at, text, query_json, top_listings_json FROM searches WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit)).fetchall()
        return [{"created_at": r[0], "text": r[1], "query": json.loads(r[2]), "top_listings": json.loads(r[3])} for r in rows]
