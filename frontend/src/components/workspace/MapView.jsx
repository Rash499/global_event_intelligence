import { useCallback, useMemo, useState } from "react";

import Globe from "../Globe.jsx";
import WeatherModeToggle from "../weather/WeatherModeToggle.jsx";
import useApiResource from "../../hooks/useApiResource";
import { getMapEvents } from "../../services/api.jsx";
import { formatCount, formatNumber, isPlottable, severityColour, severityBand } from "../../services/format.jsx";
import { Badge, ErrorState, Empty, Loading, Panel, SourceNote, Toolbar, UpdatedAt } from "./primitives.jsx";

const PRECISION_MODES = [
  { id: "coordinates", label: "Mapped locations only" },
  { id: "country", label: "Country-level only" },
  { id: "all", label: "Everything" },
];

const SCOPES = [
  { id: "major", label: "Major events" },
  { id: "all", label: "All events" },
];

const LEGEND = [
  { label: "Critical ≥ 8.5", value: 9 },
  { label: "High ≥ 6.5", value: 7 },
  { label: "Moderate ≥ 4.5", value: 5 },
  { label: "Low ≥ 2.5", value: 3 },
  { label: "Minimal", value: 1 },
];

/**
 * Map workspace.
 *
 * The map is fed by /api/map/events, which reports location precision per
 * event. Only events the source actually located are plotted as pins; events
 * known at country level are listed and shaded as country indicators, because
 * placing them at a capital would be fabricated geography.
 */
export default function MapView({
  mode = "events",
  onModeChange,
  onSelectEvent,
  onSelectCountry,
  weather,
  weatherLoading,
  onSelectWeather,
  selectedCountryCode,
  initialFilters,
}) {
  const [precision, setPrecision] = useState("all");
  // Default view: all major events of the last 7 days. "Major" is defined by
  // the backend (severity >= 6.5 or importance >= 8) and echoed back in
  // `major_definition`, so the map never shows an unexplained subset.
  const [scope, setScope] = useState("major");
  const [days, setDays] = useState(7);
  const [category, setCategory] = useState(initialFilters?.category || "");
  const [minSeverity, setMinSeverity] = useState("");

  const layer = useApiResource(
    () =>
      getMapEvents({
        days,
        precision,
        limit: scope === "major" ? 2000 : 500,
        ...(scope === "major" ? { major_only: true } : {}),
        ...(category ? { category } : {}),
        ...(minSeverity !== "" ? { min_severity: Number(minSeverity) } : {}),
      }),
    [days, precision, category, minSeverity, scope]
  );

  const items = layer.data?.items || [];

  // If the major scope matches nothing in the window, an empty globe helps
  // nobody. Fall back to all events in the same window and say so plainly
  // (fallbackActive drives the banner + coverage labels below).
  const majorEmpty =
    scope === "major" && !layer.loading && !layer.error && items.length === 0;
  const fallbackLayer = useApiResource(
    () =>
      getMapEvents({
        days,
        precision,
        limit: 500,
        ...(category ? { category } : {}),
        ...(minSeverity !== "" ? { min_severity: Number(minSeverity) } : {}),
      }),
    [days, precision, category, minSeverity],
    { enabled: majorEmpty }
  );
  const fallbackActive = majorEmpty && (fallbackLayer.data?.items || []).length > 0;
  const displayItems = fallbackActive ? fallbackLayer.data.items : items;
  const displayData = fallbackActive ? fallbackLayer.data : layer.data;

  // This is the honesty rule: a pin requires coordinates *and* a precision that
  // supports a point. Country-level rows are never given a synthetic position.
  const plottable = useMemo(
    () =>
      displayItems
        .filter((event) => isPlottable(event))
        .map((event) => ({ ...event, importance: event.severity ?? event.importance ?? 0 })),
    [displayItems]
  );

  // Country-precision events cannot be pins, but they *can* shade their
  // country. They are passed to the globe separately (polygonEvents) so the
  // map is never blank just because reporting is country-level.
  const shadingEvents = useMemo(
    () =>
      displayItems
        .filter((event) => event.country_code)
        .map((event) => ({ ...event, importance: event.severity ?? event.importance ?? 0 })),
    [displayItems]
  );

  const countryLevel = useMemo(
    () => displayItems.filter((event) => event.location_precision === "country"),
    [displayItems]
  );
  const unknownLocation = useMemo(
    () => displayItems.filter((event) => !event.location_precision || event.location_precision === "unknown"),
    [displayItems]
  );

  const shading = displayData?.country_shading || [];

  const handleCountry = useCallback(
    (country) => {
      if (mode === "weather") {
        onSelectWeather?.(country);
        return;
      }
      onSelectCountry?.(country);
    },
    [mode, onSelectCountry, onSelectWeather]
  );

  return (
    <div className="ws-view ws-map">
      <header className="ws-view-head">
        <div className="ws-title-block">
          <p className="eyebrow">GEOINT WORKSPACE</p>
          <h1>{mode === "weather" ? "Weather layer" : "Event map"}</h1>
          <p className="ws-subtitle">
            {mode === "weather"
              ? "Country conditions from Open-Meteo. The severity index is an application score, not an official warning."
              : scope === "major"
                ? `All major events from the last ${days} days (${layer.data?.major_definition || "severity ≥ 6.5 or importance ≥ 8"}). Pins only where a source reported coordinates; country-level events are shaded, not pinned.`
                : "Pins are plotted only where a source reported coordinates. Country-level events are shaded, not pinned."}
          </p>
        </div>
        <div className="ws-head-meta">
          <WeatherModeToggle mode={mode} onChange={onModeChange} />
          <UpdatedAt value={layer.updatedAt} loading={layer.loading} />
        </div>
      </header>

      {mode === "events" && (
        <Panel className="ws-filter-panel">
          <Toolbar>
            <fieldset className="ws-segmented">
              <legend>Event scope</legend>
              {SCOPES.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={scope === option.id}
                  className={scope === option.id ? "is-active" : ""}
                  onClick={() => setScope(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </fieldset>
            <fieldset className="ws-segmented">
              <legend>Location precision</legend>
              {PRECISION_MODES.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={precision === option.id}
                  className={precision === option.id ? "is-active" : ""}
                  onClick={() => setPrecision(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </fieldset>
            <label className="ws-field ws-field-narrow">
              <span>Window (days)</span>
              <input
                type="number" min="1" max="90" value={days}
                onChange={(event) => setDays(Math.max(1, Math.min(90, Number(event.target.value) || 1)))}
              />
            </label>
            <label className="ws-field ws-field-narrow">
              <span>Min severity</span>
              <input
                type="number" min="0" max="10" step="0.5" value={minSeverity}
                onChange={(event) => setMinSeverity(event.target.value)}
              />
            </label>
            <label className="ws-field">
              <span>Category</span>
              <input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="e.g. armed_conflict" />
            </label>
            <button type="button" className="ws-button" onClick={layer.reload}>Refresh</button>
          </Toolbar>
        </Panel>
      )}

      {fallbackActive && (
        <p className="ws-inline-note" role="status">
          No major events ({layer.data?.major_definition || "severity ≥ 6.5 or importance ≥ 8"}) were stored in the
          last {days} days, so the map is showing all events in that window instead. Collect more data or widen
          the window to see major events here.
        </p>
      )}

      <div className="ws-map-grid">
        <div className="ws-map-canvas">
          <Globe
            mode={mode}
            events={plottable}
            polygonEvents={shadingEvents}
            weather={weather || []}
            onSelectEvent={onSelectEvent}
            onSelectWeather={onSelectWeather}
            onSelectCountry={handleCountry}
            selectedCountryCode={selectedCountryCode}
          />
          {layer.loading && <div className="map-loading" role="status">Loading map layer…</div>}
          {layer.error && (
            <div className="ws-map-overlay">
              <ErrorState error={layer.error} onRetry={layer.reload} title="Map layer unavailable" />
            </div>
          )}
        </div>

        <aside className="ws-map-aside">
          <Panel title="Legend" eyebrow="SEVERITY BANDS">
            <ul className="ws-legend">
              {LEGEND.map((entry) => (
                <li key={entry.label}>
                  <i style={{ background: severityColour(entry.value) }} aria-hidden="true" />
                  {entry.label}
                </li>
              ))}
            </ul>
            <SourceNote>{layer.data?.legend?.note || "Location precision is reported per event."}</SourceNote>
          </Panel>

          <Panel title="Honest coverage" eyebrow="WHAT THIS MAP IS NOT SHOWING">
            <dl className="ws-facts">
              <div><dt>Plotted pins</dt><dd>{formatNumber(plottable.length)}</dd></div>
              <div><dt>Country-level events</dt><dd>{formatNumber(countryLevel.length)}</dd></div>
              <div><dt>Unknown location</dt><dd>{formatNumber(unknownLocation.length)}</dd></div>
              <div><dt>Scope</dt><dd>{scope === "major" ? `major events · last ${days}d` : `all events · last ${days}d`}</dd></div>
              <div><dt>Rows fetched</dt><dd>{formatNumber(displayItems.length)} (cap {scope === "major" && !fallbackActive ? 2000 : 500})</dd></div>
            </dl>
            {displayData?.coverage && (
              <p className="ws-muted ws-small">
                In this window the backend holds {formatCount(displayData.coverage.plotted_with_coordinates, "event")} with
                coordinates, {formatCount(displayData.coverage.country_level_only, "event")} at country level and{" "}
                {formatCount(displayData.coverage.no_location, "event")} with no location at all.
              </p>
            )}
          </Panel>

          {shading.length > 0 && (
            <Panel title="Country shading" eyebrow="COUNTRY-LEVEL EVENTS">
              <ul className="ws-rank-list">
                {shading
                  .slice()
                  .sort((a, b) => (b.max_severity || 0) - (a.max_severity || 0))
                  .slice(0, 12)
                  .map((country) => (
                    <li key={country.country_code}>
                      <button
                        type="button"
                        className="ws-link"
                        onClick={() => onSelectCountry?.({ code: country.country_code, name: country.country })}
                      >
                        {country.country || country.country_code}
                      </button>
                      <span className="ws-muted">{formatCount(country.events, "event")}</span>
                      {country.max_severity != null && (
                        <Badge colour={severityColour(country.max_severity)}>
                          {severityBand(country.max_severity)?.label || formatNumber(country.max_severity, 1)}
                        </Badge>
                      )}
                    </li>
                  ))}
              </ul>
            </Panel>
          )}

          {countryLevel.length > 0 && (
            <Panel title="Unpinned events" eyebrow="COUNTRY PRECISION ONLY">
              <ul className="ws-compact-list">
                {countryLevel.slice(0, 10).map((event) => (
                  <li key={event.id}>
                    <button type="button" className="ws-link" onClick={() => onSelectEvent?.({ id: event.id, event })}>
                      {event.title}
                    </button>
                    <span className="ws-muted">{event.country || event.country_code}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {displayItems.length === 0 && !layer.loading && !layer.error && (
            <Empty title="Nothing to plot in this window">
              {scope === "major"
                ? `No major events (${layer.data?.major_definition || "severity ≥ 6.5 or importance ≥ 8"}) were stored in the last ${days} days matching these filters. Switch to All events or widen the window.`
                : "No stored events match these filters. The map shows only collected reporting."}
            </Empty>
          )}
        </aside>
      </div>

      {weatherLoading && <p className="ws-muted">Loading weather layer…</p>}
    </div>
  );
}
