import { useCallback, useEffect, useMemo, useState } from "react";
import { getHistoricalIntelligence, compareHistoricalPeriods } from "../services/api.jsx";

const isoDaysAgo = (days) => new Date(Date.now() - days * 86400000).toISOString();
const formatCategory = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function HistoricalIntelligenceDashboard({ onBack }) {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const range = useMemo(() => ({ start: isoDaysAgo(days), end: new Date().toISOString() }), [days]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [history, compare] = await Promise.all([
        getHistoricalIntelligence(range.start, range.end),
        compareHistoricalPeriods({ start: isoDaysAgo(days * 2), end: range.start }, range),
      ]);
      setData(history);
      setComparison(compare);
    } catch (e) {
      console.error(e);
      setError("Historical intelligence could not be loaded. Check that FastAPI is running.");
    } finally {
      setLoading(false);
    }
  }, [days, range]);

  useEffect(() => { load(); }, [load]);

  const stats = data?.statistics?.summary || {};
  return (
    <section className="historical-dashboard">
      <header className="historical-header">
        <button className="back-button" onClick={onBack}>← Back to world map</button>
        <div>
          <p className="eyebrow">PHASE 4 · HISTORICAL INTELLIGENCE</p>
          <h1>Event Evolution & History</h1>
          <p>Evidence-based historical activity, reporting changes and period comparisons.</p>
        </div>
        <div className="historical-range">
          {[1, 7, 30].map((value) => (
            <button key={value} className={days === value ? "active" : ""} onClick={() => setDays(value)}>
              {value === 1 ? "24H" : \`\${value}D\`}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="notice">{error}</div>}
      {loading ? <div className="historical-loading">Loading historical intelligence...</div> : (
        <>
          <div className="historical-stats">
            {[
              ["Events", stats.events ?? 0], ["Articles", stats.articles ?? 0],
              ["Major", stats.major_events ?? 0], ["Countries", stats.countries ?? 0],
              ["Avg importance", Number(stats.average_importance || 0).toFixed(2)],
              ["Avg confidence", Number(stats.average_confidence || 0).toFixed(2)],
            ].map(([label, value]) => (
              <div className="historical-stat" key={label}><span>{label}</span><strong>{value}</strong></div>
            ))}
          </div>

          <div className="historical-grid">
            <article className="historical-card">
              <div className="historical-card-title"><span>Observed Event Activity</span><b>{data?.events?.length || 0} records</b></div>
              <div className="historical-bars">
                {(data?.events || []).slice(0, 12).map((event) => (
                  <div className="historical-bar-row" key={event.id}>
                    <span title={event.title}>{event.title}</span>
                    <i style={{ width: \`\${Math.max(4, Math.min(100, event.importance * 10))}%\` }} />
                    <b>{event.importance}/10</b>
                  </div>
                ))}
              </div>
            </article>

            <article className="historical-card">
              <div className="historical-card-title"><span>What Changed?</span><b>Period B vs Period A</b></div>
              <div className="change-summary">
                <strong>{comparison?.summary?.events_change >= 0 ? "+" : ""}{comparison?.summary?.events_change ?? 0}</strong>
                <span>events</span>
                <strong>{comparison?.summary?.articles_change >= 0 ? "+" : ""}{comparison?.summary?.articles_change ?? 0}</strong>
                <span>articles</span>
              </div>
              <ul>{(comparison?.category_changes || []).slice(0, 8).map((item) => (
                <li key={item.key}><span>{formatCategory(item.key)}</span><b>{item.before} → {item.after}</b></li>
              ))}</ul>
            </article>
          </div>

          <div className="historical-grid">
            <article className="historical-card">
              <div className="historical-card-title"><span>Category Activity</span><b>Observed counts</b></div>
              <ul className="historical-list">{(data?.statistics?.categories || []).map((item) => (
                <li key={item.category}><span>{formatCategory(item.category)}</span><b>{item.count}</b></li>
              ))}</ul>
            </article>
            <article className="historical-card">
              <div className="historical-card-title"><span>Countries</span><b>Observed events</b></div>
              <ul className="historical-list">{(data?.statistics?.countries || []).slice(0, 12).map((item) => (
                <li key={item.country_code}><span>{item.country || item.country_code || "Unknown"}</span><b>{item.count}</b></li>
              ))}</ul>
            </article>
          </div>
        </>
      )}
    </section>
  );
}
