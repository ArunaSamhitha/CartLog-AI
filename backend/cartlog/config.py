"""Settings read from environment variables (and an optional .env file).

Any missing API key switches that part of the system into mock mode, so the
whole app runs end to end with no keys at all.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    vision_model: str = field(default_factory=lambda: os.getenv("VISION_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    pinecone_api_key: str | None = field(default_factory=lambda: os.getenv("PINECONE_API_KEY"))
    pinecone_index: str = field(default_factory=lambda: os.getenv("PINECONE_INDEX", "cartlog-memory"))
    db_path: str = field(default_factory=lambda: os.getenv("CARTLOG_DB", str(Path(__file__).resolve().parents[1] / "cartlog.db")))
    agent_timeout_s: float = field(default_factory=lambda: float(os.getenv("AGENT_TIMEOUT_S", "8")))
    force_mock: bool = field(default_factory=lambda: os.getenv("CARTLOG_MOCK", "").lower() in {"1", "true", "yes"})

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key) and not self.force_mock


settings = Settings()
