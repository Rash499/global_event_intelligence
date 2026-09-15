import { useCallback, useEffect, useState } from "react";
import Globe from "./components/Globe";
import { api } from "./services/api";
import { EventItem } from "./types";
import "./styles.css";

const categories = ["all", "politics", "conflict", "natural_disaster", "economy", "technology", "health", "environment", "international"];

export default function App() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [selected, setSelected] = useState<EventItem | null>(null);
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<EventItem[]>("/events/latest?limit=100");
      setEvents(data);
      setStatus("");
    } catch {
      setStatus("Backend is not running. Start FastAPI on port 8000.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = category === "all" ? events : events.filter(e => e.category === category);

  const collect = async () => {
    setStatus("Collecting news...");
    try {
      await api.post("/ingestion/run");
      await load();
      setStatus("News collection completed.");
    } catch {
      setStatus("News collection failed. Check the backend terminal.");
    }
  };

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">AI GLOBAL EVENT INTELLIGENCE</p>
          <h1>World Event Map</h1>
          <p className="subtitle">Turn global news into structured, location-aware events.</p>
        </div>
        <button onClick={collect}>Collect News</button>
      </header>

      <section className="stats">
        <div><strong>{events.length}</strong><span>Events loaded</span></div>
        <div><strong>{events.filter(e => e.importance >= 8).length}</strong><span>Major events</span></div>
        <div><strong>{new Set(events.map(e => e.country_code).filter(Boolean)).size}</strong><span>Countries</span></div>
      </section>

      <section className="filters">
        {categories.map(c => <button className={category === c ? "active" : ""} onClick={() => setCategory(c)} key={c}>{c.replace("_", " ")}</button>)}
      </section>

      {status && <div className="notice">{status}</div>}

      <section className="workspace">
        <div className="map-panel">
          {loading ? <div className="center">Loading events...</div> : <Globe events={filtered} onSelect={setSelected} />}
        </div>

        <aside>
          <h2>{selected ? "Event Details" : "Latest Events"}</h2>
          {selected ? (
            <article className="detail">
              <span className="badge">{selected.category.replace("_", " ")}</span>
              <h3>{selected.title}</h3>
              <p>{selected.summary}</p>
              <div className="metric">Importance <b>{selected.importance}/10</b></div>
              <div className="metric">Confidence <b>{Math.round(selected.confidence * 100)}%</b></div>
              <div className="metric">Country <b>{selected.country ?? "Unknown"}</b></div>
              <button onClick={() => setSelected(null)}>Back to events</button>
            </article>
          ) : (
            <div className="event-list">
              {filtered.slice(0, 12).map(e => (
                <button className="event" key={e.id} onClick={() => setSelected(e)}>
                  <span className="score">{e.importance}</span>
                  <span><b>{e.title}</b><small>{e.country ?? "Global"} · {e.category.replace("_", " ")}</small></span>
                </button>
              ))}
              {!filtered.length && <p>No events yet. Seed demo data or collect news.</p>}
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
