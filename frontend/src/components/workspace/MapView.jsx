import { useCallback, useMemo, useState } from "react";

import Globe from "../Globe.jsx";
import FlatMap from "../globe/FlatMap.jsx";
import WeatherModeToggle from "../weather/WeatherModeToggle.jsx";
import useApiResource from "../../hooks/useApiResource";
import { getMapEvents } from "../../services/api.jsx";
import { formatCount, formatNumber, isPlottable, severityColour, severityBand } from "../../services/format.jsx";
import { formatRelativeTime } from "../../services/dateFormat.jsx";
import {
  ALL_LAYER_IDS,
  MAP_LAYERS,
  categoriesForLayers,
  layerFreshness,
} from "../globe/mapLayers.jsx";
import { clusterMapPoints } from "../globe/mapClustering.jsx";
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
  // Map layers (registry in ../globe/mapLayers.jsx): all on by default. The
  // selection is sent to the backend as a taxonomy `categories` filter so
  // pins, country shading and coverage figures all agree.
  const [enabledLayers, setEnabledLayers] = useState(ALL_LAYER_IDS);
  const [clustering, setClustering] = useState(true);
  const [selectedCluster, setSelectedCluster] = useState(null);
  // Dual map surface (worldmonitor pattern): 3D globe or flat 2D map, same
  // data and click routing either way.
  const [viewMode, setViewMode] = useState("globe");
  // Time replay: when set, only events that had occurred by
  // (window start + replayDays) are shown. Null = live (whole window).
  const [replayDays, setReplayDays] = useState(null);

  const allLayersOn = enabledLayers.length === MAP_LAYERS.length;
  const categoriesParam = useMemo(
    () => (allLayersOn ? null : categoriesForLayers(enabledLayers).join(",")),
    [allLayersOn, enabledLayers]
  );

  const toggleLayer = useCallback((layerId) => {
    setSelectedCluster(null);
    setEnabledLayers((current) =>
      current.includes(layerId)
        ? current.filter((id) => id !== layerId)
        : [...current, layerId]
    );
  }, []);

  const layer = useApiResource(
    () =>
      getMapEvents({
        days,
        precision,
        limit: scope === "major" ? 2000 : 500,
        ...(scope === "major" ? { major_only: true } : {}),
        ...(categoriesParam !== null ? { categories: categoriesParam } : {}),
        ...(category ? { category } : {}),
        ...(minSeverity !== "" ? { min_severity: Number(minSeverity) } : {}),
      }),
    [days, precision, category, minSeverity, scope, categoriesParam]
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
        ...(categoriesParam !== null ? { categories: categoriesParam } : {}),
        ...(category ? { category } : {}),
        ...(minSeverity !== "" ? { min_severity: Number(minSeverity) } : {}),
      }),
    [days, precision, category, minSeverity, categoriesParam],
    { enabled: majorEmpty }
  );
  const fallbackActive = majorEmpty && (fallbackLayer.data?.items || []).length > 0;
  const displayItems = fallbackActive ? fallbackLayer.data.items : items;
  const displayData = fallbackActive ? fallbackLayer.data : layer.data;

  // Time replay works over the already-fetched rows: an event is visible
  // when its occurrence time is at or before the replay cutoff. Events
  // without an occurrence time are hidden during replay (and counted in
  // the replay note) rather than silently kept or dropped.
  const replayActive = replayDays !== null && replayDays < days;
  const replayCutoffMs = useMemo(
    () =>
      replayActive
        ? Date.now() - (days - replayDays) * 24 * 60 * 60 * 1000
        : null,
    [replayActive, replayDays, days]
  );
  const visibleItems = useMemo(() => {
    if (!replayActive || replayCutoffMs === null) return displayItems;
    return displayItems.filter((event) => {
      const t = event.occurred_at ? Date.parse(event.occurred_at) : NaN;
      return Number.isFinite(t) && t <= replayCutoffMs;
    });
  }, [displayItems, replayActive, replayCutoffMs]);
  const replayHiddenCount = displayItems.length - visibleItems.length;

  // This is the honesty rule: a pin requires coordinates *and* a precision that
  // supports a point. Country-level rows are never given a synthetic position.
  const plottable = useMemo(
    () =>
      visibleItems
        .filter((event) => isPlottable(event))
        .map((event) => ({ ...event, importance: event.severity ?? event.importance ?? 0 })),
    [visibleItems]
  );

  // Country-precision events cannot be pins, but they *can* shade their
  // country. They are passed to the globe separately (polygonEvents) so the
  // map is never blank just because reporting is country-level.
  const shadingEvents = useMemo(
    () =>
      visibleItems
        .filter((event) => event.country_code)
        .map((event) => ({ ...event, importance: event.severity ?? event.importance ?? 0 })),
    [visibleItems]
  );

  const countryLevel = useMemo(
    () => visibleItems.filter((event) => event.location_precision === "country"),
    [visibleItems]
  );
  const unknownLocation = useMemo(
    () => visibleItems.filter((event) => !event.location_precision || event.location_precision === "unknown"),
    [visibleItems]
  );

  const shading = displayData?.country_shading || [];

  // Country aggregates (worldmonitor-style): every country-level event is
  // visible on the globe as a distinct country bubble at the country's
  // display anchor, labelled with its count - never disguised as a pin.
  // Suppressed in "coordinates" precision mode, where the user explicitly
  // asked for located incidents only.
  // During replay the backend shading describes the whole window, so the
  // aggregates are regrouped from the visible country-level rows instead
  // (positions still come from the backend's country display anchors).
  const replayShading = useMemo(() => {
    if (!replayActive) return null;
    const anchors = new Map(
      shading
        .filter((row) => row.latitude != null && row.longitude != null)
        .map((row) => [row.country_code, row])
    );
    const grouped = new Map();
    for (const event of countryLevel) {
      const anchor = anchors.get(event.country_code);
      if (!anchor) continue;
      const entry =
        grouped.get(event.country_code) ||
        {
          country_code: event.country_code,
          country: event.country || anchor.country,
          events: 0,
          max_severity: null,
          latitude: anchor.latitude,
          longitude: anchor.longitude,
          is_country_aggregate: true,
        };
      entry.events += 1;
      if (event.severity != null) {
        entry.max_severity =
          entry.max_severity == null ? event.severity : Math.max(entry.max_severity, event.severity);
      }
      grouped.set(event.country_code, entry);
    }
    return [...grouped.values()];
  }, [replayActive, shading, countryLevel]);

  const effectiveShading = replayShading ?? shading;

  const aggregatePoints = useMemo(
    () =>
      precision === "coordinates"
        ? []
        : effectiveShading
            .filter((row) => row.latitude != null && row.longitude != null)
            .map((row) => ({
              id: `country-aggregate-${row.country_code}`,
              title: `${row.events} event${row.events === 1 ? "" : "s"} in ${row.country || row.country_code}`,
              country: row.country,
              country_code: row.country_code,
              latitude: row.latitude,
              longitude: row.longitude,
              importance: row.max_severity ?? 0,
              aggregate_count: row.events,
              is_country_aggregate: true,
            })),
    [effectiveShading, precision]
  );

  // Nearby pins are merged into disclosed cluster markers (position = the
  // average of the reported locations) so dense regions stay readable.
  // Aggregates are appended unclustered: they are already country rollups.
  const pinPoints = useMemo(
    () => (clustering ? clusterMapPoints(plottable) : plottable),
    [clustering, plottable]
  );
  const clusterPoints = useMemo(
    () => pinPoints.filter((point) => point.is_cluster),
    [pinPoints]
  );

  const globeEvents = useMemo(
    () => [...pinPoints, ...aggregatePoints],
    [pinPoints, aggregatePoints]
  );

  const freshness = displayData?.freshness;
  const layerStats = useMemo(
    () => layerFreshness(freshness?.category_freshness || []),
    [freshness]
  );

  const handleGlobeSelect = useCallback(
    (event) => {
      if (event?.is_cluster) {
        setSelectedCluster(event);
        return;
      }
      if (event?.is_country_aggregate) {
        onSelectCountry?.({ code: event.country_code, name: event.country });
        return;
      }
      setSelectedCluster(null);
      onSelectEvent?.(event);
    },
    [onSelectEvent, onSelectCountry]
  );

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
          <fieldset className="ws-segmented">
            <legend>Map view</legend>
            {[
              { id: "globe", label: "Globe" },
              { id: "flat", label: "Flat map" },
            ].map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={viewMode === option.id}
                className={viewMode === option.id ? "is-active" : ""}
                onClick={() => setViewMode(option.id)}
              >
                {option.label}
              </button>
            ))}
          </fieldset>
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
                onChange={(event) => {
                  setDays(Math.max(1, Math.min(90, Number(event.target.value) || 1)));
                  setReplayDays(null);
                }}
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
            <label className="ws-field">
              <span>
                Time replay{" "}
                {replayActive
                  ? `— up to ${new Date(replayCutoffMs).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
                  : "— live"}
              </span>
              <input
                type="range"
                min="0"
                max={days}
                step="0.25"
                value={replayDays ?? days}
                aria-label="Time replay position in the selected window"
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setReplayDays(value >= days ? null : value);
                  setSelectedCluster(null);
                }}
              />
            </label>
            {replayActive && (
              <button type="button" className="ws-button" onClick={() => setReplayDays(null)}>
                Back to live
              </button>
            )}
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

      {replayActive && (
        <p className="ws-inline-note" role="status">
          Time replay: showing {formatCount(visibleItems.length, "event")} that had occurred by{" "}
          {new Date(replayCutoffMs).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} —{" "}
          {formatCount(replayHiddenCount, "event")} later in (or undated in) the fetched window{" "}
          {replayHiddenCount === 1 ? "is" : "are"} hidden, and country aggregates are regrouped for this
          point in time.
        </p>
      )}

      <div className="ws-map-grid">
        <div className="ws-map-canvas">
          {viewMode === "globe" ? (
            <Globe
              mode={mode}
              events={globeEvents}
              polygonEvents={shadingEvents}
              weather={weather || []}
              onSelectEvent={handleGlobeSelect}
              onSelectWeather={onSelectWeather}
              onSelectCountry={handleCountry}
              selectedCountryCode={selectedCountryCode}
            />
          ) : (
            <FlatMap
              mode={mode}
              events={globeEvents}
              polygonEvents={shadingEvents}
              weather={weather || []}
              onSelectEvent={handleGlobeSelect}
              onSelectCountry={handleCountry}
              selectedCountryCode={selectedCountryCode}
            />
          )}
          {layer.loading && <div className="map-loading" role="status">Loading map layer…</div>}
          {layer.error && (
            <div className="ws-map-overlay">
              <ErrorState error={layer.error} onRetry={layer.reload} title="Map layer unavailable" />
            </div>
          )}
        </div>

        <aside className="ws-map-aside">
          {mode === "events" && (
            <Panel title="Map layers" eyebrow="STORED EVENT LAYERS">
              <ul className="ws-layer-list">
                {MAP_LAYERS.map((mapLayer) => {
                  const on = enabledLayers.includes(mapLayer.id);
                  const stats = layerStats[mapLayer.id] || { events: 0, latest_event_at: null };
                  return (
                    <li key={mapLayer.id}>
                      <button
                        type="button"
                        aria-pressed={on}
                        className={on ? "is-active" : ""}
                        title={mapLayer.description}
                        onClick={() => toggleLayer(mapLayer.id)}
                      >
                        <span aria-hidden="true">{mapLayer.glyph}</span> {mapLayer.label}
                      </button>
                      <span className="ws-muted">
                        {formatCount(stats.events, "event")}
                        {stats.latest_event_at ? ` · ${formatRelativeTime(stats.latest_event_at)}` : ""}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <label className="ws-layer-toggle">
                <input
                  type="checkbox"
                  checked={clustering}
                  onChange={(event) => { setClustering(event.target.checked); setSelectedCluster(null); }}
                />
                Cluster nearby pins
              </label>
              <SourceNote>
                Layers filter stored events by taxonomy category — no new data source is
                fetched. Counts show events stored in this window per layer, with the
                most recent one. Latest event:{" "}
                {freshness?.latest_event_at ? formatRelativeTime(freshness.latest_event_at) : "—"} ·
                last collection:{" "}
                {freshness?.latest_ingestion_at ? formatRelativeTime(freshness.latest_ingestion_at) : "—"}.
              </SourceNote>
            </Panel>
          )}

          {selectedCluster && (
            <Panel title="Clustered events" eyebrow="NEARBY PINS GROUPED">
              <p className="ws-muted ws-small">
                These {formatCount(selectedCluster.cluster_count, "event")} were reported close
                together; the marker sits at the average of their reported locations, which is
                not itself an event location.
              </p>
              <ul className="ws-compact-list">
                {(selectedCluster.events || []).map((event) => (
                  <li key={event.id}>
                    <button type="button" className="ws-link" onClick={() => onSelectEvent?.({ id: event.id, event })}>
                      {event.title}
                    </button>
                    <span className="ws-muted">{event.country || event.country_code || ""}</span>
                  </li>
                ))}
              </ul>
              <button type="button" className="ws-button" onClick={() => setSelectedCluster(null)}>
                Close cluster
              </button>
            </Panel>
          )}

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
              <div><dt>Pin clusters</dt><dd>{formatNumber(clusterPoints.length)}</dd></div>
              <div><dt>Layers on</dt><dd>{enabledLayers.length}/{MAP_LAYERS.length}</dd></div>
              <div><dt>Country aggregates</dt><dd>{formatNumber(aggregatePoints.length)}</dd></div>
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

          {effectiveShading.length > 0 && (
            <Panel title="Country shading" eyebrow="COUNTRY-LEVEL EVENTS">
              {replayActive && (
                <p className="ws-muted ws-small">Counts at the replay point in time.</p>
              )}
              <ul className="ws-rank-list">
                {effectiveShading
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
