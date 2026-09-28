import { useEffect, useId, useMemo, useState } from "react";

import {
  loadWorldGeoJSON,
  matchCountryFeatures,
  normalizeCountryCode,
} from "../../services/worldGeoJson.jsx";
import CountryMapControls from "./CountryMapControls.jsx";
import CountryMapPins from "./CountryMapPins.jsx";
import {
  buildMap,
  clusterRings,
  collectRings,
  finite,
  MAX_PINS,
  SEVERITY_LEVELS,
  severityColor,
  severityLevel,
  VIEW_H,
  VIEW_W,
} from "./countryMapProjection.jsx";
import CountryMapTooltip from "./CountryMapTooltip.jsx";

/** Re-export projection math for backwards compatibility with existing importers / tests */
export { buildMap, clusterRings, severityLevel };

export default function CountryEventMap({
  country,
  events = [],
  activeEventId = null,
  onSelect,
}) {
  const [features, setFeatures] = useState(null);
  const [outlineState, setOutlineState] = useState("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [hoveredId, setHoveredId] = useState(null);

  const gradientId = `country-map-fill-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;

  const code = normalizeCountryCode(country?.code) || "";
  const name = country?.name || "";
  const scopeKey = `${code}|${name}`;
  const eventCount = Array.isArray(events) ? events.length : 0;

  useEffect(() => {
    let alive = true;
    setOutlineState("loading");

    loadWorldGeoJSON()
      .then((data) => {
        if (!alive) return;
        setFeatures(data?.features || []);
        setOutlineState("ready");
      })
      .catch((error) => {
        if (!alive) return;
        console.error("Failed to load world.geojson for the country map:", error);
        setFeatures([]);
        setOutlineState("error");
      });

    return () => {
      alive = false;
    };
  }, [reloadKey]);

  useEffect(() => {
    setZoom(1);
    setHoveredId(null);
  }, [scopeKey]);

  const matches = useMemo(
    () => (features ? matchCountryFeatures(features, code, name) : []),
    [features, code, name]
  );

  const shapeInfo = useMemo(() => {
    const rings = matches.flatMap((match) => collectRings(match.feature?.geometry));
    return clusterRings(rings);
  }, [matches]);

  const locatedEvents = useMemo(
    () =>
      (events || [])
        .map((event) => ({
          event,
          lat: finite(event?.latitude),
          lng: finite(event?.longitude),
        }))
        .filter((entry) => entry.lat !== null && entry.lng !== null)
        .slice(0, MAX_PINS),
    [events]
  );

  const map = useMemo(
    () => buildMap(shapeInfo.rings, locatedEvents.map(({ lng, lat }) => ({ lng, lat }))),
    [shapeInfo, locatedEvents]
  );

  const pins = useMemo(() => {
    if (!map) return [];

    return locatedEvents.map(({ event, lat, lng }) => {
      const [x, y] = map.project([lng, lat]);
      const safeX = Number.isFinite(x) ? x : VIEW_W / 2;
      const safeY = Number.isFinite(y) ? y : VIEW_H / 2;

      return {
        id: String(event?.id ?? `${lat}:${lng}`),
        event,
        lat,
        lng,
        x: safeX,
        y: safeY,
        level: severityLevel(event?.importance),
        color: severityColor(event?.importance),
        onMap: safeX >= -8 && safeX <= VIEW_W + 8 && safeY >= -8 && safeY <= VIEW_H + 8,
      };
    });
  }, [locatedEvents, map]);

  const severityCounts = useMemo(() => {
    const counts = { critical: 0, high: 0, moderate: 0, low: 0 };
    pins.forEach((pin) => {
      counts[pin.level] += 1;
    });
    return counts;
  }, [pins]);

  const hoveredPin = hoveredId ? pins.find((pin) => pin.id === hoveredId) || null : null;
  const unmapped = eventCount - locatedEvents.length;
  const zoomTransform = `translate(${VIEW_W / 2} ${VIEW_H / 2}) scale(${zoom}) translate(${-VIEW_W / 2} ${-VIEW_H / 2})`;

  const statusLabel =
    outlineState === "loading"
      ? "loading outline…"
      : outlineState === "error"
        ? "outline unavailable"
        : matches.length
          ? `${shapeInfo.kept}/${shapeInfo.total} outline shapes`
          : "outline not matched";

  if (!map) {
    return (
      <div className="country-map-panel">
        <div className="country-map-head">
          <div>
            <span className="section-eyebrow">EVENT GEOGRAPHY</span>
            <h3>Where the signals are</h3>
          </div>
        </div>
        <p className="country-map-empty">
          {outlineState === "loading"
            ? `Loading the outline for ${name || code || "this country"}…`
            : `No located events for ${name || code || "this country"} yet. Coordinates appear once the ingestion pipeline geocodes a report.`}
        </p>
      </div>
    );
  }

  return (
    <div className="country-map-panel">
      <div className="country-map-head">
        <div>
          <span className="section-eyebrow">EVENT GEOGRAPHY</span>
          <h3>Where the signals are</h3>
        </div>
        <CountryMapControls
          zoom={zoom}
          onZoomChange={setZoom}
          onReset={() => {
            setZoom(1);
            setHoveredId(null);
          }}
        />
      </div>

      <div className="country-map-canvas">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="country-map-svg"
          role="img"
          aria-label={`Event locations across ${name || code || "this country"}`}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0.65" y2="1">
              <stop offset="0%" stopColor="rgba(46, 134, 175, 0.46)" />
              <stop offset="100%" stopColor="rgba(9, 42, 64, 0.68)" />
            </linearGradient>
          </defs>

          <g transform={zoomTransform}>
            <g className="country-map-grid-layer" aria-hidden="true">
              {map.grid.map((line) => (
                <g key={line.key}>
                  <line
                    className="country-map-grid"
                    x1={line.x1}
                    y1={line.y1}
                    x2={line.x2}
                    y2={line.y2}
                  />
                  <text
                    className="country-map-grid-label"
                    x={line.labelX}
                    y={line.labelY}
                    textAnchor={line.labelX === 6 ? "start" : "middle"}
                  >
                    {line.label}
                  </text>
                </g>
              ))}
            </g>

            {map.fallback ? (
              <rect
                className="country-map-box"
                x={map.box.x}
                y={map.box.y}
                width={map.box.width}
                height={map.box.height}
                rx="6"
              />
            ) : (
              <path className="country-map-outline" d={map.path} fill={`url(#${gradientId})`} />
            )}

            <CountryMapPins
              pins={pins}
              activeEventId={activeEventId}
              hoveredId={hoveredId}
              onSelect={onSelect}
              onHover={setHoveredId}
            />

            <CountryMapTooltip hoveredPin={hoveredPin} />
          </g>
        </svg>

        <div className="country-map-overlay">
          <span
            className={`country-map-chip ${
              outlineState === "error" || map.fallback ? "is-warn" : ""
            }`}
          >
            {statusLabel}
          </span>
          <span className="country-map-chip">{pins.length} located</span>
        </div>
      </div>

      <div className="country-map-legend">
        {SEVERITY_LEVELS.map((level) => (
          <span key={level.key}>
            <i style={{ background: level.color, color: level.color }} />
            {level.label} {severityCounts[level.key]}
          </span>
        ))}
      </div>

      <div className="country-map-foot">
        <span>
          {pins.length} of {eventCount} events mapped
          {unmapped > 0 ? ` · ${unmapped} without coordinates` : ""}
          {map.fallback ? " · sampling box view" : ""}
        </span>
        {outlineState === "error" ? (
          <button
            type="button"
            className="country-map-btn country-map-btn-wide"
            onClick={() => setReloadKey((value) => value + 1)}
          >
            Retry outline
          </button>
        ) : null}
      </div>
    </div>
  );
}

