import { useEffect, useRef, useState } from "react";

const AGENT_LABELS = { research: "Research", ebay: "eBay", amazon: "Amazon" };
const EXAMPLES = ["used sony headphones under $200", "mechanical keyboard under $120", "standing desk"];

function loadSession() {
  try {
    return localStorage.getItem("cartlog-session") || null;
  } catch {
    return null;
  }
}

function saveSession(id) {
  try {
    localStorage.setItem("cartlog-session", id);
  } catch {
    /* private mode: session lasts for this tab only */
  }
}

async function postJSON(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Request failed (${res.status})`);
  return res.json();
}

async function postImage(file, note, sessionId) {
  const form = new FormData();
  form.append("image", file);
  if (note) form.append("note", note);
  if (sessionId) form.append("session_id", sessionId);
  const res = await fetch("/api/search/image", { method: "POST", body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Upload failed (${res.status})`);
  return res.json();
}

const money = (n, currency = "USD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(n);

export default function App() {
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [sessionId, setSessionId] = useState(loadSession);
  const fileInput = useRef(null);

  useEffect(() => {
    if (!photo) return setPreview(null);
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  async function run(searchText = text) {
    if (!photo && !searchText.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = photo
        ? await postImage(photo, searchText.trim(), sessionId)
        : await postJSON("/api/search", { text: searchText.trim(), session_id: sessionId });
      setResult(data);
      setSessionId(data.session_id);
      saveSession(data.session_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true">◧</span> CartLog AI
        </div>
        <p className="tagline">Snap a product or describe it. Research, eBay and Amazon agents search at the same time.</p>
      </header>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <button type="button" className="camera" onClick={() => fileInput.current?.click()} aria-label="Add a product photo">
          {preview ? <img src={preview} alt="Selected product" /> : <span>＋ Photo</span>}
        </button>
        <input
          ref={fileInput}
          id="photo"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          hidden
          onChange={(e) => setPhoto(e.target.files?.[0] || null)}
        />
        <input
          id="query"
          className="query"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={photo ? "Optional: budget or details, e.g. under $80" : "What are you looking for?"}
          maxLength={500}
        />
        {photo && (
          <button type="button" className="ghost" onClick={() => setPhoto(null)}>
            Remove photo
          </button>
        )}
        <button className="go" disabled={loading || (!photo && !text.trim())}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {!result && !loading && (
        <div className="examples">
          Try:{" "}
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" onClick={() => { setText(ex); run(ex); }}>
              {ex}
            </button>
          ))}
        </div>
      )}

      {error && <p className="error" role="alert">{error}</p>}

      {result && <Results data={result} onRecall={(t) => { setText(t); run(t); }} />}
    </div>
  );
}

export function Results({ data, onRecall }) {
  const { query, listings, research, timings, parse_ms, total_ms, mock_mode, remembered } = data;
  const slowest = Math.max(...timings.map((t) => t.ms), 1);

  return (
    <main className="results">
      {mock_mode && <p className="mock">Demo data: add API keys in backend/.env for live marketplace results.</p>}

      <section className="understood">
        <h2>Searching for</h2>
        <div className="pills">
          <span className="pill strong">{[query.brand, query.model, query.product].filter(Boolean).join(" ")}</span>
          {query.attributes.map((a) => <span className="pill" key={a}>{a}</span>)}
          {query.max_price != null && <span className="pill">under {money(query.max_price)}</span>}
          {query.condition !== "any" && <span className="pill">{query.condition}</span>}
        </div>
        {remembered.length > 0 && (
          <div className="recall">
            Related past searches:{" "}
            {remembered.map((r) => <button key={r} className="chip" onClick={() => onRecall(r)}>{r}</button>)}
          </div>
        )}
      </section>

      <section className="trace" aria-label="Agent timings">
        <div className="trace-head">
          <span>agents ran in parallel</span>
          <span>understand {parse_ms.toFixed(0)} ms · total {total_ms.toFixed(0)} ms</span>
        </div>
        {timings.map((t) => (
          <div className="trace-row" key={t.agent}>
            <span className="trace-name">{AGENT_LABELS[t.agent] || t.agent}</span>
            <span className="trace-track">
              <span className={`trace-bar ${t.ok ? "" : "failed"}`} style={{ width: `${(t.ms / slowest) * 100}%` }} />
            </span>
            <span className="trace-ms">{t.ok ? `${t.ms.toFixed(0)} ms` : t.error}</span>
          </div>
        ))}
      </section>

      {research && (
        <section className="research">
          <h2>What reviewers say</h2>
          <p>{research.summary}</p>
          {research.typical_price_range && (
            <p className="range">
              Typical price: {money(research.typical_price_range[0])} – {money(research.typical_price_range[1])}
            </p>
          )}
          {research.sources.length > 0 && (
            <ul className="sources">
              {research.sources.map((s) => <li key={s}><a href={s} target="_blank" rel="noreferrer">{new URL(s).hostname}</a></li>)}
            </ul>
          )}
        </section>
      )}

      <section>
        <h2>{listings.length} listings, best match first</h2>
        {listings.length === 0 && <p className="empty">Nothing matched. Try raising the budget or removing a detail.</p>}
        <ol className="grid">
          {listings.map((l, i) => (
            <li className="card" key={`${l.marketplace}-${l.title}-${l.price}-${i}`}>
              {l.image_url ? <img src={l.image_url} alt="" loading="lazy" /> : <div className="noimg" aria-hidden="true" />}
              <div className="card-body">
                <span className={`market ${l.marketplace}`}>{l.marketplace === "ebay" ? "eBay" : "Amazon"}</span>
                <a className="title" href={l.url} target="_blank" rel="noreferrer">{l.title}</a>
                <div className="meta">
                  <strong>{money(l.price, l.currency)}</strong>
                  {l.condition && <span>{l.condition}</span>}
                  {l.rating && <span>★ {l.rating}</span>}
                  <span className="score" title="Match score: relevance, value and rating">{Math.round(l.score * 100)}</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
