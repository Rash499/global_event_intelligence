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
const clamp100 = (value) => Math.min(100, Math.max(0, Number(value) || 0));

// Weights mirror the backend scoring model (25/30/20/25) so the ledger shown to
// the user reconciles with the headline 0-100 score.
const FACTOR_WEIGHTS = { temperature: 0.25, precipitation: 0.3, wind: 0.2, severe_weather: 0.25 };
const FACTOR_ORDER = ["temperature", "precipitation", "wind", "severe_weather"];
const FACTOR_META = {
  temperature: { label: "Temperature", metric: "Current, focus-day max and min" },
  precipitation: { label: "Precipitation", metric: "Rain volume plus probability" },
  wind: { label: "Wind", metric: "Sustained speed and gusts" },
  severe_weather: { label: "Severe weather", metric: "WMO weather code severity" },
};

const FACTOR_BANDS = {
  temperature: [
    { min: 95, note: "Extreme thermal stress: 45°C or hotter, or -15°C or colder." },
    { min: 84, note: "Severe heat above 40°C with elevated health risk." },
    { min: 72, note: "Hard freeze between -5°C and -15°C." },
    { min: 66, note: "High heat between 35°C and 40°C." },
    { min: 48, note: "Freezing readings between 0°C and -5°C." },
    { min: 42, note: "Elevated heat between 32°C and 35°C." },
    { min: 1, note: "Mild thermal discomfort, no extreme band reached." },
    { min: 0, note: "Comfortable range: no heat or cold contribution." },
  ],
  precipitation: [
    { min: 80, note: "Extreme rainfall: flooding and transport disruption likely." },
    { min: 60, note: "Very heavy rain or near-certain downpours expected." },
    { min: 40, note: "Heavy rain spells with standing water possible." },
    { min: 20, note: "Moderate rain, disruptive but manageable." },
    { min: 1, note: "Light rain or low rainfall probability." },
    { min: 0, note: "Dry conditions across the sampled horizon." },
  ],
  wind: [
    { min: 75, note: "Damaging wind: structural damage and travel bans possible." },
    { min: 55, note: "Severe wind, gusts strong enough to down trees and power lines." },
    { min: 35, note: "Strong wind: loose objects airborne, ferries and flights at risk." },
    { min: 18, note: "Gusty spells, mostly a nuisance rather than a hazard." },
    { min: 1, note: "Breezy but well inside normal limits." },
    { min: 0, note: "Calm wind profile." },
  ],
  severe_weather: [
    { min: 90, note: "Thunderstorm code present in the sampled conditions." },
    { min: 65, note: "Violent showers, heavy snow or hail codes present." },
    { min: 35, note: "Moderate severe codes: heavy rain or snow showers." },
    { min: 15, note: "Light rain or snow codes only." },
    { min: 0, note: "No severe weather codes reported." },
  ],
};

function bandNote(bands, value) {
  const score = clamp100(value);
  for (let i = 0; i < bands.length; i += 1) {
    if (score >= bands[i].min) return bands[i].note;
  }
  return bands[bands.length - 1].note;
}

function explainFactor(key, value) {
  return bandNote(FACTOR_BANDS[key] || FACTOR_BANDS.temperature, value);
}

function readingFor(key, current = {}, focus = null) {
  const now = current || {};
  const ahead = focus || {};
  if (key === "temperature") {
    return `now ${num(now.temperature_2m)}°C (feels ${num(now.apparent_temperature)}°C) · focus day ${num(ahead.temperature_max)}°C max / ${num(ahead.temperature_min)}°C min`;
  }
  if (key === "precipitation") {
    return `now ${num(now.precipitation)} mm at ${num(now.precipitation_probability, 0)}% · focus day ${num(ahead.precipitation_sum)} mm at ${num(ahead.precipitation_probability_max, 0)}%`;
  }
  if (key === "wind") {
    return `now ${num(now.wind_speed_10m)} km/h, gusts ${num(now.wind_gusts_10m)} km/h · focus day ${num(ahead.wind_speed_max)} km/h, gusts ${num(ahead.wind_gusts_max)} km/h`;
  }
  return `now code ${num(now.weather_code)} (${now.weather_description || "no description"}) · focus day code ${num(ahead.weather_code)} (${ahead.weather_description || "no description"})`;
}

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
function factorRanking(factors = {}) {
  return FACTOR_ORDER.map((key) => {
    const value = clamp100(factors[key]);
    const weight = FACTOR_WEIGHTS[key];
    return { key, value, weight, contribution: value * weight };
  }).sort((a, b) => b.contribution - a.contribution);
}

function peakIndex(daily = []) {
  let best = 0;
  daily.forEach((entry, index) => {
    if ((Number(entry?.score) || 0) > (Number(daily[best]?.score) || 0)) best = index;
  });
  return best;
}

function FactorRow({ factorKey, value, weight, contribution, share, rank, current, focus }) {
  const meta = FACTOR_META[factorKey] || { label: factorKey, metric: "" };
  const precise = Math.round(Number(value) * 10) / 10;
  return (
    <div className={`risk-factor detailed ${rank === 0 ? "is-top" : ""}`}>
      <div className="risk-factor-heading">
        <span>
          {meta.label}
          {rank === 0 ? <em className="risk-tag">top driver</em> : null}
        </span>
        <strong>{precise}<small>/100</small></strong>
      </div>
      <div className="risk-bar"><span style={{ width: `${clamp100(value)}%` }} /></div>
      <p className="risk-explain">{explainFactor(factorKey, value)}</p>
      <dl className="risk-ledger">
        <div><dt>Weight</dt><dd>{Math.round(weight * 100)}%</dd></div>
        <div><dt>Weighted points</dt><dd>{contribution.toFixed(1)} of 100</dd></div>
        <div><dt>Share of total</dt><dd>{Math.round(share)}%</dd></div>
        <div className="wide"><dt>Sample</dt><dd>{readingFor(factorKey, current, focus)}</dd></div>
      </dl>
    </div>
  );
}

function ScoreSpark({ daily = [], day, onPick }) {
  const peak = peakIndex(daily);
  return (
    <div className="score-spark" role="group" aria-label="Daily risk scores">
      {daily.map((entry, index) => (
        <button
          key={entry.date}
          type="button"
          className={`spark-bar ${severityClass(entry.severity)} ${index === day ? "on" : ""} ${index === peak ? "is-peak" : ""}`}
          style={{ height: `${Math.max(6, clamp100(entry.score))}%` }}
          onClick={() => onPick(index)}
          title={`${fmtDate(entry.date)} - ${Math.round(Number(entry.score) || 0)}/100 (${entry.severity})`}
        >
          <span>{Math.round(Number(entry.score) || 0)}</span>
        </button>
      ))}
    </div>
  );
}

function ReadingRow({ label, value, detail }) {
  return (
    <li>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{detail}</em>
    </li>
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
  const ranking = useMemo(() => factorRanking(factors), [factors]);
  const weightedTotal = Math.max(1, ranking.reduce((sum, item) => sum + item.contribution, 0));
  const peak = peakIndex(daily);
  const peakDay = daily[peak] || null;
  const topDriver = ranking[0] || null;
  const verdict = useMemo(() => {
    if (!weather) return "";
    const parts = [];
    parts.push(
      `${weather.country || "This area"} scores ${Math.round(weather.score || 0)}/100 (${weather.severity})${rank.pos ? `, rank #${rank.pos} of ${rank.total}` : ""}.`
    );
    if (topDriver) {
      const label = FACTOR_META[topDriver.key]?.label || topDriver.key;
      parts.push(
        `${label} is the strongest driver after weighting: ${Math.round(topDriver.value)}/100 × ${Math.round(topDriver.weight * 100)}% = ${topDriver.contribution.toFixed(1)} weighted points.`
      );
    }
    parts.push(
      `Current conditions read ${Math.round(weather.current_score || 0)}/100 while the ${daily.length}-day peak reaches ${Math.round(weather.forecast_score || 0)}/100${peakDay ? ` on ${fmtDate(peakDay.date)}` : ""}.`
    );
    return parts.join(" ");
  }, [weather, topDriver, rank.pos, rank.total, peakDay, daily.length]);
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
            <div className="weather-section-heading">
              <div><span className="section-eyebrow">RISK BREAKDOWN</span><h3>Why ranked here</h3></div>
              <span className={`chip ${severityClass(weather.severity)}`}>{Math.round(weather.score || 0)}/100 · {weather.severity}</span>
            </div>
            <p className="risk-verdict">{verdict}</p>
            <div className="risk-factors summary">
              {ranking.map((item) => (
                <RiskBar
                  key={item.key}
                  label={FACTOR_META[item.key]?.label || item.key}
                  value={item.value}
                  hint={`${Math.round(item.weight * 100)}% weight · ${item.contribution.toFixed(1)} weighted pts (${Math.round((item.contribution / weightedTotal) * 100)}% of total)`}
                />
              ))}
            </div>
            <div className="risk-factors detailed-list">
              {ranking.map((item, index) => (
                <FactorRow
                  key={item.key}
                  factorKey={item.key}
                  value={item.value}
                  weight={item.weight}
                  contribution={item.contribution}
                  share={(item.contribution / weightedTotal) * 100}
                  rank={index}
                  current={weather.current}
                  focus={focus}
                />
              ))}
            </div>
            <div className="risk-ledger-total">
              <span>{ranking.map((item) => `${Math.round(item.weight * 100)}% × ${Math.round(item.value)}`).join("  +  ")}</span>
              <strong>{weightedTotal.toFixed(1)} weighted pts → headline {Math.round(weather.score || 0)}/100</strong>
            </div>
            <div className="risk-extra">
              <div className="risk-extra-block">
                <span className="section-eyebrow">NOW VS FOCUS DAY</span>
                <ul className="reading-list">
                  <ReadingRow
                    label="Condition now"
                    value={weather.current?.weather_description || "-"}
                    detail={`${toT(weather.current?.temperature_2m)} · feels ${toT(weather.current?.apparent_temperature)} · code ${num(weather.current?.weather_code)}`}
                  />
                  <ReadingRow
                    label="Rain and wind now"
                    value={`${num(weather.current?.precipitation)} mm`}
                    detail={`${num(weather.current?.precipitation_probability, 0)}% chance · wind ${num(weather.current?.wind_speed_10m)} km/h, gusts ${num(weather.current?.wind_gusts_10m)} km/h`}
                  />
                  <ReadingRow
                    label={focus ? fmtDate(focus.date) : "Focus day"}
                    value={focus?.weather_description || "-"}
                    detail={focus
                      ? `${toT(focus.temperature_max)} / ${toT(focus.temperature_min)} · ${num(focus.precipitation_sum)} mm · wind ${num(focus.wind_speed_max)} km/h, gusts ${num(focus.wind_gusts_max)} km/h`
                      : "no forecast day selected"}
                  />
                  <ReadingRow
                    label="Peak of horizon"
                    value={peakDay ? fmtDate(peakDay.date) : "-"}
                    detail={peakDay ? `${Math.round(peakDay.score)}/100 · ${peakDay.severity} · ${peakDay.weather_description}` : "no forecast available"}
                  />
                  <ReadingRow
                    label="Reporting point"
                    value={weather.timezone || "n/a"}
                    detail={`${num(weather.latitude)}°, ${num(weather.longitude)}° · source Open-Meteo`}
                  />
                </ul>
              </div>
              <div className="risk-extra-block">
                <span className="section-eyebrow">DAILY RISK SHAPE</span>
                <ScoreSpark daily={daily} day={day} onPick={setDay} />
                <p className="risk-note">
                  Bar height tracks the 0-100 daily score. The highlighted bar is the day shown in Day Focus;
                  the outlined bar is the peak of the horizon.
                </p>
              </div>
            </div>
            <details className="risk-footnotes">
              <summary>How this 0-100 score is built</summary>
              <ul>
                <li>Temperature 25% · Precipitation 30% · Wind 20% · Severe weather 25%.</li>
                <li>Precipitation carries the heaviest weight because rain volume drives flooding and mobility disruption.</li>
                <li>Each factor is scored 0-100, multiplied by its weight, then summed into the headline score.</li>
                <li>Now values come from the Open-Meteo sample point for this area; the 7-day outlook defines the forecast peak and the daily shape above.</li>
                <li>City samples on the mini map are separate Open-Meteo calls for the capital and largest metros, so a capital can read differently from the country sample.</li>
              </ul>
            </details>
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
