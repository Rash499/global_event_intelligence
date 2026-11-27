import { useCallback, useMemo, useState } from "react";

import Globe from "../Globe.jsx";
import WeatherModeToggle from "../weather/WeatherModeToggle.jsx";
import useApiResource from "../../hooks/useApiResource";
import { getMapEvents } from "../../services/api.jsx";
import { formatCount, formatNumber, severityColour, severityBand } from "../../services/format.jsx";
import { Badge, ErrorState, Empty, Loading, Panel, SourceNote, Toolbar, UpdatedAt } from "./primitives.jsx";

const PRECISION_MODES = [
  { id: "coordinates", label: "Mapped locations only" },
  { id: "country", label: "Country-level only" },
  { id: "all", label: "Everything" },
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
  const [days, setDays] = useState(7);
  const [category, setCategory] = useState(initialFilters?.category || "");
  const [minSeverity, setMinSeverity] = useState("");

  const layer = useApiResource(
    () =>
      getMapEvents({
        days,
        precision,
        limit: 500,
        ...(category ? { category } : {}),
        ...(minSeverity !== "" ? { min_severity: Number(minSeverity) } : {}),
      }),
    [days, precision, category, minSeverity]
  );

  const items = layer.data?.items || [];

  // This is the honesty rule: a pin requires coordinates *and* a precision that
  // supports a point. Country-level rows are never given a synthetic position.
  const plottable = useMemo(
    () =>
      items
        .filter(
          (event) =>
            event.latitude !== null &&
            event.longitude !== null &&
            ["exact", "city", "locality", "region"].includes(event.location_precision)
        )
        .map((event) => ({ ...event, importance: event.severity ?? event.importance ?? 0 })),
    [items]
  );

  const countryLevel = useMemo(
    () => items.filter((event) => event.location_precision === "country"),
    [items]
  );
  const unknownLocation = useMemo(
    () => items.filter((event) => !event.location_precision || event.location_precision === "unknown"),
    [items]
  );

  const shading = layer.data?.country_shading || [];

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

      <div className="ws-map-grid">
        <div className="ws-map-canvas">
          <Globe
            mode={mode}
            events={plottable}
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
              <div><dt>Rows fetched</dt><dd>{formatNumber(items.length)} (cap 500)</dd></div>
            </dl>
            {layer.data?.coverage && (
              <p className="ws-muted ws-small">
                In this window the backend holds {formatCount(layer.data.coverage.plotted_with_coordinates, "event")} with
                coordinates, {formatCount(layer.data.coverage.country_level_only, "event")} at country level and{" "}
                {formatCount(layer.data.coverage.no_location, "event")} with no location at all.
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

          {items.length === 0 && !layer.loading && !layer.error && (
            <Empty title="Nothing to plot in this window">
              No stored events match these filters. The map shows only collected reporting.
            </Empty>
          )}
        </aside>
      </div>

      {weatherLoading && <p className="ws-muted">Loading weather layer…</p>}
    </div>
  );
}
