# How CartLog works: design notes and interview prep

Read this before talking about the project. Each section is a question you're likely to be asked, with the answer and the file to point at.

## "Walk me through a request."

`service.py` is the whole pipeline in about 40 lines:

1. `understanding.parse_image` / `parse_text` → a `ProductQuery` (Pydantic model in `schemas.py`).
2. `Orchestrator.run(query)` fans out to three MCP servers. At the same time, `Memory.recall` looks up related past searches. Both run under one `asyncio.gather`.
3. `ranking.rank` merges eBay and Amazon listings, removes duplicates and scores them.
4. `Memory.remember` stores the search and its embedding.
5. The response includes timings per agent, the time spent understanding the request, and the total.

## "Why MCP instead of just calling the APIs from one service?"

- **Isolation:** each agent is its own process with its own dependencies and credentials. A crash or a slow API in the Amazon agent can't block the event loop of the API server.
- **A standard interface:** every agent exposes typed tools (`search_ebay(query, max_price, condition, limit)`), and the tool schema comes from the Python type hints. Adding a Walmart agent means writing one more server and adding one line to `AGENTS` in `orchestrator.py`.
- **Reuse:** the same servers work in any MCP client, for example as tools in an AI desktop app or an IDE.

The trade-off is a little overhead per call (JSON-RPC over stdio) and one process per agent. Sessions are opened once at startup (the FastAPI `lifespan` in `api.py`), so searches don't pay the start-up cost.

## "How does the parallelism work, and how did you measure it?"

`Orchestrator.run` uses `asyncio.gather` over one coroutine per agent. Each coroutine wraps `session.call_tool` in `asyncio.wait_for(…, timeout)` and catches every exception, so `gather` never raises. A failed agent becomes an `AgentTiming(ok=False, error=…)`.

`benchmark.py` runs the same queries with `parallel=True` and `parallel=False` against the same open sessions and reports the median and p95 for each. With simulated agent latencies of about 0.7, 0.9 and 1.1 s, sequential takes the sum (about 2.6 s) and parallel takes the maximum (about 1.1 s), a 59% cut. Be clear in interviews that this number comes from simulated latencies. The script measures live APIs once keys are set.

**Follow-up:** *"Why not threads?"* The work is I/O-bound (waiting on HTTP and pipes), so async is the natural fit with no locking.

## "How does photo search work?"

`parse_image` base64-encodes the image into a data URL and sends it to the chat completions API with `response_format={"type": "json_object"}` and a system prompt that describes the `ProductQuery` fields. The JSON is validated with Pydantic, so a malformed answer fails loudly instead of sending bad queries to the agents. `detail: "low"` keeps the vision call fast and cheap. A photo of a product doesn't need high-res tiles unless you want to read small print.

## "Tell me about the RAG / memory part."

Each search is embedded (`text-embedding-3-small`, or a hashed bag of words and character trigrams when there's no key) and stored. `recall` finds the most similar past searches **in the same session** above a similarity threshold. Pinecone gets a metadata filter on `session_id`, and the local store filters in SQL. Results show up as "Related past searches" chips.

Why the keyless fallback is a hashed embedding: it keeps the feature testable offline and in CI. It only captures word overlap, which is fine for "sony headphones" vs "sony wh-1000xm5 headphones" but would miss "earbuds" vs "in-ear headphones".

## "How do you rank results?"

`score = 0.6 · relevance + 0.3 · value + 0.1 · rating`

- Relevance: the share of query words found in the title. It drops by 30% when the listing's condition doesn't match the request.
- Value: 0.5 at the typical price (the middle of the research agent's price range, or the budget), rising toward 1 for cheaper listings and falling toward 0 at double the typical price.
- Rating: mapped from 3–5 stars to 0–1, and neutral when a listing has no rating.

**Honest weakness:** the weights are hand-picked. The next step would be logging clicks and learning the weights.

## "What would you do next?"

- Stream results to the UI as each agent finishes (Server-Sent Events) instead of waiting for the slowest one.
- Cache identical queries for a few minutes, since marketplace prices don't change by the second.
- Add evals: a set of labeled product photos to measure how often the vision step extracts the right brand and model.
- Price alerts using the stored history.
