import { useEffect, useMemo, useState } from "react";

const severityClass = (s = "normal") => String(s || "normal").toLowerCase();
const fmtDate = (v) => {
  if (!v) return "-";
  const d = new Date(`${v}T00:00:00`);
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(d);
};
const num = (v, d = "-") => (Number.isFinite(Number(v)) ? Number(v) : d);

const iconFor = (desc = "") => {
  const t = desc.toLowerCase();
  if (t.includes("thunder")) return "⛈️";
  if (t.includes("snow") || t.includes("blizzard")) return "❄️";
  if (t.includes("rain") || t.includes("drizzle") || t.includes("shower")) return "🌧️";
  if (t.includes("fog") || t.includes("mist") || t.includes("haze")) return "🌫️";
  if (t.includes("cloud") || t.includes("overcast")) return "☁️";
  if (t.includes("clear") || t.includes("sun")) return "☀️";
  return "🌤️";
};
function RiskBar({ label, value, hint }) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setW(Math.min(100, Math.max(0, value || 0))));
    return () => cancelAnimationFrame(id);
  }, [value]);
  return (
    <div className="risk-factor" title={hint || `${label}: ${Math.round(value || 0)}/100`}>
      <div className="risk-factor-heading"><span>{label}</span><strong>{Math.round(value || 0)}</strong></div>
      <div className="risk-bar"><span style={{ width: `${w}%` }} /></div>
      {hint && <small className="risk-hint">{hint}</small>}
    </div>
  );
}
function Metric({ icon, label, big, sub, title }) {
  return (
    <div className="weather-current-card weather-metric" title={title || label}>
      <span className="metric-icon" aria-hidden="true">{icon}</span>
      <span>{label}</span>
      <strong>{big}</strong>
      <small>{sub}</small>
    </div>
  );
}
export default function WeatherDashboard({ weather, weatherList, miniMap, onBack, onSelect }) {
  const list = weatherList || [];
  const [tab, setTab] = useState("overview");
  const [day, setDay] = useState(0);
  const [unit, setUnit] = useState("C");
  const [copied, setCopied] = useState(false);
  const daily = weather?.daily || [];
  const factors = weather?.risk_factors || {};
  useEffect(() => { setTab("overview"); setDay(0); setCopied(false); }, [weather?.country_code]);
  useEffect(() => { if (day >= daily.length) setDay(0); }, [daily.length, day]);
  const toT = (c) => (c === null || c === undefined ? "-" : unit === "C" ? `${Math.round(Number(c))}C` : `${Math.round(Number(c) * 9 / 5 + 32)}F`);
  const rank = useMemo(() => {
    const sorted = [...list].sort((a, b) => (b.score || 0) - (a.score || 0));
    const i = sorted.findIndex((w) => w.country_code === weather?.country_code);
    return { pos: i >= 0 ? i + 1 : null, total: sorted.length };
  }, [list, weather]);
  const focus = daily[day] || null;
  const share = async () => {
    const text = `${weather?.country} weather: ${weather?.current?.weather_description}, ${weather?.current?.temperature_2m}C, score ${Math.round(weather?.score || 0)}/100.`;
    try { await navigator.clipboard.writeText(text); } catch { /* noop */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  if (!weather) return null;
  return (
    <section className="weather-dashboard is-live">
      <header className="weather-dashboard-header">
        <div className="brief-top">
          <button className="back-button" onClick={onBack}>Back to weather map</button>
          <div className="brief-actions">
            <div className="unit-toggle" role="group" aria-label="Temperature unit">
              <button type="button" className={unit === "C" ? "on" : ""} onClick={() => setUnit("C")}>C</button>
              <button type="button" className={unit === "F" ? "on" : ""} onClick={() => setUnit("F")}>F</button>
            </div>
            <button type="button" className="ghost-btn" onClick={share}>{copied ? "Copied" : "Share briefing"}</button>
          </div>
        </div>
        <div className="brief-hero">
          <div>
            <span className="country-code">{weather.country_code || "GLOBAL"} / WEATHER BRIEF</span>
            <h2>{weather.country || "Weather Area"}</h2>
            <p className="brief-sub">{iconFor(weather.current?.weather_description)} {weather.current?.weather_description || "Current"} - {toT(weather.current?.temperature_2m)} - feels {toT(weather.current?.apparent_temperature)}</p>
            <div className="brief-chips">
              <span className={`chip ${severityClass(weather.severity)}`}>{weather.severity} - {Math.round(weather.score || 0)}/100</span>
              {rank.pos && <span className="chip ghost">Rank #{rank.pos} of {rank.total}</span>}
              {weather.timezone && <span className="chip ghost">{weather.timezone}</span>}
            </div>
          </div>
          <div className={`weather-dashboard-score ${severityClass(weather.severity)}`}>
            <strong>{Math.round(weather.score || 0)}</strong>
            <span>{weather.severity}</span>
            <small>now {Math.round(weather.current_score || 0)} - peak {Math.round(weather.forecast_score || 0)}</small>
          </div>
        </div>
        <div className="brief-tabs" role="tablist" aria-label="Briefing views">
          <button type="button" role="tab" aria-selected={tab === "overview"} className={`brief-tab ${tab === "overview" ? "on" : ""}`} onClick={() => setTab("overview")}>Overview</button>
          <button type="button" role="tab" aria-selected={tab === "forecast"} className={`brief-tab ${tab === "forecast" ? "on" : ""}`} onClick={() => setTab("forecast")}>Forecast ({daily.length})</button>
          <button type="button" role="tab" aria-selected={tab === "compare"} className={`brief-tab ${tab === "compare" ? "on" : ""}`} onClick={() => setTab("compare")}>Compare</button>
        </div>
      </header>
      <div className="weather-current-grid">
        <Metric icon="T" label="Current condition" big={weather.current?.weather_description || "-"} sub={`${toT(weather.current?.temperature_2m)} - feels ${toT(weather.current?.apparent_temperature)}`} />
        <Metric icon="R" label="Precipitation" big={`${num(weather.current?.precipitation)} mm`} sub={`${num(weather.current?.precipitation_probability, 0)}% probability`} />
        <Metric icon="W" label="Wind" big={`${num(weather.current?.wind_speed_10m)} km/h`} sub={`Gusts ${num(weather.current?.wind_gusts_10m)} km/h`} />
        <Metric icon="P" label="Forecast peak" big={`${Math.round(weather.forecast_score || 0)} / 100`} sub="Highest daily severity" />
      </div>
      {tab === "overview" && (
        <div className="weather-dashboard-grid brief-grid">
          <div className="weather-section">
            <div className="weather-section-heading"><div><span className="section-eyebrow">RISK BREAKDOWN</span><h3>Why ranked here</h3></div></div>
            <div className="risk-factors">
              <RiskBar label="Temperature" value={factors.temperature} hint="Heat and cold stress." />
              <RiskBar label="Precipitation" value={factors.precipitation} hint="Rain amount plus probability." />
              <RiskBar label="Wind" value={factors.wind} hint="Sustained wind and gusts." />
              <RiskBar label="Severe weather" value={factors.severe_weather} hint="Storm and snow codes." />
            </div>
          </div>
          <div className="brief-side">
            {miniMap}
            <div className="weather-section day-focus">
              <span className="section-eyebrow">DAY FOCUS</span>
              <h3>{focus ? fmtDate(focus.date) : "No forecast"}</h3>
              {focus && (<><p className="day-focus-main">{focus.weather_description}</p><em className={`forecast-risk ${severityClass(focus.severity)}`}>{Math.round(focus.score)} / 100</em></>)}
              <div className="day-stepper">
                <button type="button" disabled={day <= 0} onClick={() => setDay((v) => Math.max(0, v - 1))}>Prev</button>
                <span>{daily.length ? `${day + 1} / ${daily.length}` : "0 / 0"}</span>
                <button type="button" disabled={day >= daily.length - 1} onClick={() => setDay((v) => Math.min(daily.length - 1, v + 1))}>Next</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {tab === "forecast" && (
        <div className="weather-section">
          <div className="weather-section-heading"><div><span className="section-eyebrow">FORECAST</span><h3>Next {daily.length} days</h3></div></div>
          <div className="forecast-list is-clickable">
            {daily.map((d2, i) => (
              <button type="button" key={d2.date} onClick={() => setDay(i)} className={`forecast-card as-btn ${i === day ? "on" : ""}`}>
                <strong>{fmtDate(d2.date)}</strong>
                <span>{d2.weather_description}</span>
                <b>{d2.temperature_max}C / {d2.temperature_min}C</b>
                <em className={`forecast-risk ${severityClass(d2.severity)}`}>{Math.round(d2.score)} / 100</em>
              </button>
            ))}
          </div>
        </div>
      )}
      {tab === "compare" && (
        <div className="weather-section">
          <div className="weather-section-heading"><div><span className="section-eyebrow">COMPARE</span><h3>Jump to another area</h3></div></div>
          <div className="compare-list">
            {[...list].sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 8).map((w) => (
              <button key={w.country_code} type="button" disabled={!onSelect} onClick={() => onSelect && onSelect(w)} className={`compare-row ${w.country_code === weather.country_code ? "on" : ""}`}>
                <span className={`weather-score sm ${severityClass(w.severity)}`}>{Math.round(w.score || 0)}</span>
                <span className="compare-copy"><strong>{w.country}</strong><small>{w.current?.weather_description}</small></span>
                <span className={`weather-severity ${severityClass(w.severity)}`}>{w.severity}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
