"""Runs the marketplace and research agents as MCP servers and calls them in parallel.

Each agent is a separate MCP server process (stdio transport). The orchestrator
starts them once, keeps the sessions open, and fans every search out to all
agents with asyncio.gather, so the total wait is the slowest agent rather than
the sum of all of them. Each call has its own timeout, and one failing agent
never takes down the whole search.
"""
import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import settings
from .schemas import AgentTiming, ProductQuery

SERVERS_DIR = Path(__file__).resolve().parents[1] / "mcp_servers"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    script: str
    tool: str


AGENTS = [
    AgentSpec("research", "research_server.py", "research_product"),
    AgentSpec("ebay", "ebay_server.py", "search_ebay"),
    AgentSpec("amazon", "amazon_server.py", "search_amazon"),
]


def _tool_args(agent: str, query: ProductQuery) -> dict:
    text = query.search_string()
    if agent == "research":
        return {"query": text}
    args = {"query": text, "max_price": query.max_price}
    if agent == "ebay":
        args["condition"] = query.condition
    return args


def _parse_result(result) -> dict:
    """MCP tool results arrive as structured content or as JSON text blocks."""
    if getattr(result, "is_error", False):
        text = " ".join(getattr(c, "text", "") for c in result.content)
        raise RuntimeError(text or "tool returned an error")
    structured = getattr(result, "structured_content", None)
    if structured:
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise RuntimeError("tool returned no content")


class Orchestrator:
    def __init__(self, agents: list[AgentSpec] = AGENTS, timeout_s: float | None = None):
        self.agents = agents
        self.timeout_s = timeout_s or settings.agent_timeout_s
        self.sessions: dict[str, ClientSession] = {}
        self._stack: AsyncExitStack | None = None

    async def start(self) -> None:
        """Spawn every MCP server and complete the MCP handshake, all at once."""
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        async def connect(spec: AgentSpec):
            params = StdioServerParameters(command=sys.executable, args=[str(SERVERS_DIR / spec.script)])
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            return spec.name, session

        # Contexts must be entered on one task, so connect sequentially but quickly.
        for spec in self.agents:
            name, session = await connect(spec)
            self.sessions[name] = session

    async def stop(self) -> None:
        if self._stack:
            await self._stack.__aexit__(None, None, None)
            self._stack = None
            self.sessions.clear()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()

    async def _call(self, spec: AgentSpec, query: ProductQuery) -> tuple[str, dict | None, AgentTiming]:
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.sessions[spec.name].call_tool(spec.tool, _tool_args(spec.name, query)),
                timeout=self.timeout_s,
            )
            data = _parse_result(result)
            return spec.name, data, AgentTiming(agent=spec.name, ms=_ms(t0), ok=True)
        except asyncio.TimeoutError:
            return spec.name, None, AgentTiming(agent=spec.name, ms=_ms(t0), ok=False, error=f"timed out after {self.timeout_s}s")
        except Exception as exc:  # one agent failing must not fail the search
            return spec.name, None, AgentTiming(agent=spec.name, ms=_ms(t0), ok=False, error=str(exc)[:200])

    async def run(self, query: ProductQuery, parallel: bool = True) -> tuple[dict[str, dict], list[AgentTiming]]:
        """Call every agent. `parallel=False` exists only for the benchmark."""
        if parallel:
            outcomes = await asyncio.gather(*(self._call(spec, query) for spec in self.agents))
        else:
            outcomes = [await self._call(spec, query) for spec in self.agents]
        results = {name: data for name, data, _ in outcomes if data is not None}
        timings = [timing for _, _, timing in outcomes]
        return results, timings


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)
