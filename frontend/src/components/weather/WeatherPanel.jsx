import { useMemo, useState } from "react";
const sev = (s = "normal") => String(s || "normal").toLowerCase();
const labelFor = (score) => {
  if (score >= 81) return "Extreme";
  if (score >= 61) return "High";
  if (score >= 41) return "Moderate";
  if (score >= 21) return "Low";
  return "Normal";
};
const iconFor = (d = "") => {
  const t = String(d).toLowerCase();
  if (t.includes("thunder")) return "⛈";
  if (t.includes("snow")) return "❄";
  if (t.includes("rain") || t.includes("drizzle")) return "🌧";
  if (t.includes("fog")) return "🌫";
  if (t.includes("cloud")) return "☁";
  if (t.includes("clear")) return "☀";
  return "🌤";
};
export default function WeatherPanel({ weather, onSelect, selectedCode }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("score");
  const [expanded, setExpanded] = useState(false);
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    let out = [...(weather || [])];
    if (filter !== "all") out = out.filter((w) => sev(w.severity) === filter);
    if (term) out = out.filter((w) => `${w.country || ""} ${w.country_code || ""}`.toLowerCase().includes(term));
    if (sort === "score") out.sort((a, b) => (b.score || 0) - (a.score || 0));
    if (sort === "temp") out.sort((a, b) => (b.current?.temperature_2m || 0) - (a.current?.temperature_2m || 0));
    if (sort === "wind") out.sort((a, b) => (b.current?.wind_speed_10m || 0) - (a.current?.wind_speed_10m || 0));
    if (sort === "name") out.sort((a, b) => String(a.country || "").localeCompare(String(b.country || "")));
    return out;
  }, [weather, q, filter, sort]);
  const shown = expanded ? rows.slice(0, 30) : rows.slice(0, 12);
  const top = weather && weather.length ? Math.max(...weather.map((w) => w.score || 0)) : 0;
  return (
    <aside className="latest-panel weather-panel is-live">
      <div className="panel-header">
        <div><p className="eyebrow">WEATHER INTELLIGENCE</p><h2>Critical Areas</h2></div>
        <span>{weather.length}</span>
      </div>
      <p className="weather-panel-note">Ranked by current plus forecast severity. Application index, not an official warning.</p>
      <div className="wx-controls">
        <input className="wx-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search country or code..." aria-label="Search critical areas" />
        <div className="wx-chip-row" role="group" aria-label="Severity filter">
          {["all", "extreme", "high", "moderate", "low", "normal"].map((f) => (
            <button key={f} type="button" className={`wx-chip ${filter === f ? "on" : ""} ${f}`} onClick={() => setFilter(f)}>{f === "all" ? "All" : f}</button>
          ))}
        </div>
        <div className="wx-sort-row">
          <label>Sort <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort critical areas"><option value="score">Top score</option><option value="temp">Hottest</option><option value="wind">Windiest</option><option value="name">Name A-Z</option></select></label>
          <span className="wx-count">{shown.length} / {rows.length} shown - peak {Math.round(top)}</span>
        </div>
      </div>
      <div className="weather-list">
        {shown.map((item, idx) => (
          <button type="button" key={`${item.country_code}-${item.latitude}-${item.longitude}`} onClick={() => onSelect(item)} className={`weather-row ${selectedCode === item.country_code ? "on" : ""}`}>
            <span className="wx-rank">#{idx + 1}</span>
            <span className={`weather-score ${sev(item.severity)}`}>{Math.round(item.score || 0)}</span>
            <span className="weather-row-copy">
              <strong>{iconFor(item.current?.weather_description)} {item.country || item.country_code || "Unknown"}</strong>
              <small>{item.current?.temperature_2m ?? "-"}C - {item.current?.weather_description || "Unknown"} - wind {item.current?.wind_speed_10m ?? "-"} km/h</small>
              <span className="wx-meter"><span style={{ width: `${Math.min(100, Math.max(0, item.score || 0))}%` }} /></span>
            </span>
            <span className={`weather-severity ${sev(item.severity)}`}>{item.severity || labelFor(item.score)}</span>
          </button>
        ))}
        {!shown.length && <div className="wx-empty">No areas match this search/filter.</div>}
      </div>
      {rows.length > 12 && (
        <button type="button" className="wx-more" onClick={() => setExpanded((v) => !v)}>{expanded ? "Show top 12" : `Show more (${Math.min(30, rows.length)} of ${rows.length})`}</button>
      )}
    </aside>
  );
}
