import { useEffect, useId, useMemo, useState } from "react";

import {
  loadWorldGeoJSON,
  matchCountryFeatures,
  normalizeCountryCode,
} from "../../services/worldGeoJson.jsx";

const VIEW_W = 520;
const VIEW_H = 340;
const PAD = 18;
/** Rings further than this (in degrees) from the main landmass are dropped. */
const CLUSTER_TOLERANCE_DEG = 6;
/** Sampled outlines keep the SVG cheap while staying recognisable. */
const MAX_RING_POINTS = 1400;
const MAX_PINS = 150;

const SEVERITY_LEVELS = [
  { key: "critical", label: "Critical", color: "#ff5d7a" },
  { key: "high", label: "High", color: "#ff9f43" },
  { key: "moderate", label: "Moderate", color: "#ffd166" },
  { key: "low", label: "Low", color: "#36b8ff" },
];

/** Exported for reuse/testing of the projection maths. */
export { buildMap, clusterRings, severityLevel };

function finite(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function severityLevel(importance) {
  const value = finite(importance);
  // Mirrors EventCard.getSeverity so map pins match the card impact badge.
  if (value === null) return "low";
  if (value >= 8) return "critical";
  if (value >= 6) return "high";
  if (value >= 4) return "moderate";
  return "low";
}

function severityColor(importance) {
  const level = severityLevel(importance);
  const entry = SEVERITY_LEVELS.find((level_) => level_.key === level) || SEVERITY_LEVELS[2];
  return entry.color;
}

function shortLabel(value, max = 30) {
  const text = String(value ?? "").trim();
  if (!text) return "Untitled event";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function collectRings(geometry) {
  if (!geometry || !geometry.coordinates) return [];
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

function validRing(ring, maxPoints = MAX_RING_POINTS) {
  const points = (ring || []).filter(
    (point) => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])
  );

  if (points.length <= maxPoints) return points;

  const stride = Math.ceil(points.length / maxPoints);
  const sampled = [];
  for (let index = 0; index < points.length; index += stride) sampled.push(points[index]);
  const last = points[points.length - 1];
  if (sampled[sampled.length - 1] !== last) sampled.push(last);
  return sampled;
}

function ringBounds(ring) {
  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  let points = 0;

  (ring || []).forEach((point) => {
    const lng = finite(point?.[0]);
    const lat = finite(point?.[1]);
    if (lng === null || lat === null) return;
    points += 1;
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  });

  return points ? { minLng, maxLng, minLat, maxLat, points } : null;
}

// Wrap-aware longitude gap so antimeridian neighbours still count as touching.
function lngGap(a, b) {
  let best = Infinity;
  [-360, 0, 360].forEach((offset) => {
    const gap = Math.max(a.minLng + offset - b.maxLng, b.minLng - (a.maxLng + offset), 0);
    if (gap < best) best = gap;
  });
  return best;
}

function boundsGap(a, b) {
  return {
    latGap: Math.max(a.minLat - b.maxLat, b.minLat - a.maxLat, 0),
    lngGap: lngGap(a, b),
  };
}

// Keep the connected landmass carrying the most detail and drop outlying
// territories (e.g. French Guiana for France) so the view stays on the country.
function clusterRings(rings, tolerance = CLUSTER_TOLERANCE_DEG) {
  const items = (rings || [])
    .map((ring) => {
      const bounds = ringBounds(ring);
      return bounds ? { ring, ...bounds } : null;
    })
    .filter(Boolean);

  if (!items.length) return { rings: [], total: 0, kept: 0, dropped: 0 };

  const ordered = [...items].sort((left, right) => right.points - left.points);
  const cluster = [ordered[0]];
  const window = { ...ordered[0] };
  let growing = true;

  while (growing) {
    growing = false;
    for (let index = 1; index < ordered.length; index += 1) {
      const item = ordered[index];
      if (cluster.includes(item)) continue;
      const gap = boundsGap(window, item);
      if (gap.latGap > tolerance || gap.lngGap > tolerance) continue;
      cluster.push(item);
      window.minLng = Math.min(window.minLng, item.minLng);
      window.maxLng = Math.max(window.maxLng, item.maxLng);
      window.minLat = Math.min(window.minLat, item.minLat);
      window.maxLat = Math.max(window.maxLat, item.maxLat);
      growing = true;
    }
  }

  return {
    rings: cluster.map((entry) => entry.ring),
    total: items.length,
    kept: cluster.length,
    dropped: items.length - cluster.length,
  };
}

function buildGrid(map) {
  const lines = [];
  const spanLng = map.maxLng - map.minLng;
  const spanLat = map.maxLat - map.minLat;
  const lngStep = spanLng > 60 ? 10 : spanLng > 20 ? 5 : 2;
  const latStep = spanLat > 40 ? 10 : spanLat > 12 ? 5 : 2;

  for (
    let lng = Math.ceil(map.minLng / lngStep) * lngStep;
    lng <= map.maxLng;
    lng += lngStep
  ) {
    const [x1, y1] = map.project([lng, map.minLat]);
    const [x2, y2] = map.project([lng, map.maxLat]);
    lines.push({
      key: `lng-${lng.toFixed(1)}`,
      x1,
      y1,
      x2,
      y2,
      label: `${Math.round(lng)}°`,
      labelX: (x1 + x2) / 2,
      labelY: VIEW_H - 5,
    });
  }

  for (
    let lat = Math.ceil(map.minLat / latStep) * latStep;
    lat <= map.maxLat;
    lat += latStep
  ) {
    const [x1, y1] = map.project([map.minLng, lat]);
    const [x2, y2] = map.project([map.maxLng, lat]);
    lines.push({
      key: `lat-${lat.toFixed(1)}`,
      x1,
      y1,
      x2,
      y2,
      label: `${Math.round(lat)}°`,
      labelX: 6,
      labelY: (y1 + y2) / 2 - 3,
    });
  }

  return lines;
}


/**
 * Fit the outline (plus any anchors) into the SVG view box. Longitudes are
 * unwrapped around a reference point so antimeridian countries render as one
 * continuous shape instead of splitting across the projection seam.
 */
function buildMap(rings, anchors = []) {
  const points = [];
  (rings || []).forEach((ring) => validRing(ring).forEach((point) => points.push(point)));

  const anchorList = (anchors || []).filter(
    (anchor) => finite(anchor?.lng) !== null && finite(anchor?.lat) !== null
  );

  const refLng = anchorList.length
    ? finite(anchorList[0].lng)
    : points.length
      ? points[0][0]
      : 0;

  const shift = (lng) => {
    let value = lng;
    while (value - refLng > 180) value -= 360;
    while (value - refLng < -180) value += 360;
    return value;
  };

  const projected = points.map(([lng, lat]) => [shift(lng), lat]);
  anchorList.forEach((anchor) => projected.push([shift(finite(anchor.lng)), finite(anchor.lat)]));

  if (!projected.length) return null;

  let minLng = Infinity;
  let maxLng = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;

  projected.forEach(([lng, lat]) => {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  });

  // No outline matched: widen a sampling box around the known points so the
  // panel still renders something meaningful instead of an empty canvas.
  const fallback = !points.length;
  const minSpan = fallback ? 4 : 0.6;

  if (maxLng - minLng < minSpan) {
    const mid = (minLng + maxLng) / 2;
    minLng = mid - minSpan / 2;
    maxLng = mid + minSpan / 2;
  }
  if (maxLat - minLat < minSpan) {
    const mid = (minLat + maxLat) / 2;
    minLat = mid - minSpan / 2;
    maxLat = mid + minSpan / 2;
  }

  const spanLng = maxLng - minLng;
  const spanLat = maxLat - minLat;
  const scale = Math.min((VIEW_W - PAD * 2) / spanLng, (VIEW_H - PAD * 2) / spanLat);
  const offX = (VIEW_W - spanLng * scale) / 2;
  const offY = (VIEW_H - spanLat * scale) / 2;

  const project = ([lng, lat]) => [
    offX + (shift(lng) - minLng) * scale,
    offY + (maxLat - lat) * scale,
  ];

  const path = (rings || [])
    .map((ring) => {
      const coords = validRing(ring).map((point) => project(point));
      if (!coords.length) return "";
      const [first, ...rest] = coords;
      return (
        `M ${first[0].toFixed(1)} ${first[1].toFixed(1)}` +
        rest.map((point) => ` L ${point[0].toFixed(1)} ${point[1].toFixed(1)}`).join("") +
        " Z"
      );
    })
    .filter(Boolean)
    .join(" ");

  const box = {
    x: offX,
    y: offY,
    width: Math.max(spanLng * scale, 1),
    height: Math.max(spanLat * scale, 1),
  };

  const map = {
    path,
    project,
    fallback,
    spanLng,
    spanLat,
    minLng,
    maxLng,
    minLat,
    maxLat,
    box,
  };

  map.grid = buildGrid(map);
  return map;
}


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

  const tooltipText = hoveredPin ? shortLabel(hoveredPin.event?.title, 34) : "";
  const tooltipWidth = clamp(tooltipText.length * 6.4 + 28, 150, 300);

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
        <div className="country-map-controls">
          <button
            type="button"
            className="country-map-btn"
            aria-label="Zoom in"
            disabled={zoom >= 6}
            onClick={() => setZoom((value) => Math.min(6, Number((value + 0.5).toFixed(1))))}
          >
            +
          </button>
          <button
            type="button"
            className="country-map-btn"
            aria-label="Zoom out"
            disabled={zoom <= 1}
            onClick={() => setZoom((value) => Math.max(1, Number((value - 0.5).toFixed(1))))}
          >
            −
          </button>
          <button
            type="button"
            className="country-map-btn country-map-btn-wide"
            onClick={() => {
              setZoom(1);
              setHoveredId(null);
            }}
          >
            Reset
          </button>
          <span className="country-map-zoom-label">{zoom.toFixed(1)}×</span>
        </div>
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


            {pins.map((pin) => {
              const isActive = activeEventId !== null && String(activeEventId) === pin.id;
              const isHovered = hoveredId === pin.id;

              return (
                <g
                  key={pin.id}
                  className={`country-map-pin ${isActive ? "is-active" : ""} ${
                    isHovered ? "is-hover" : ""
                  } ${pin.onMap ? "" : "is-off-view"}`}
                  transform={`translate(${pin.x} ${pin.y})`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${shortLabel(pin.event?.title, 60)} — ${pin.level} importance`}
                  onClick={(pointerEvent) => {
                    pointerEvent.stopPropagation();
                    onSelect?.(pin.event);
                  }}
                  onKeyDown={(keyEvent) => {
                    if (keyEvent.key !== "Enter" && keyEvent.key !== " ") return;
                    keyEvent.preventDefault();
                    onSelect?.(pin.event);
                  }}
                  onMouseEnter={() => setHoveredId(pin.id)}
                  onFocus={() => setHoveredId(pin.id)}
                  onMouseLeave={() =>
                    setHoveredId((current) => (current === pin.id ? null : current))
                  }
                  onBlur={() => setHoveredId((current) => (current === pin.id ? null : current))}
                >
                  <title>{shortLabel(pin.event?.title, 80)}</title>
                  {isActive ? (
                    <circle className="country-map-pin-pulse" r="7" style={{ color: pin.color }} />
                  ) : null}
                  <circle
                    className="country-map-pin-halo"
                    r={isActive || isHovered ? 12 : 8.5}
                    fill={pin.color}
                  />
                  <circle
                    className="country-map-pin-core"
                    r={isActive || isHovered ? 4.4 : 3.2}
                    fill={pin.color}
                  />
                </g>
              );
            })}

            {hoveredPin ? (
              <g
                className="country-map-tip"
                transform={`translate(${clamp(
                  hoveredPin.x,
                  tooltipWidth / 2 + 6,
                  VIEW_W - tooltipWidth / 2 - 6
                )} ${clamp(hoveredPin.y - 32, 24, VIEW_H - 10)})`}
                aria-hidden="true"
              >
                <rect x={-tooltipWidth / 2} y="-19" width={tooltipWidth} height="36" rx="8" />
                <text textAnchor="middle" y="-5">
                  {tooltipText}
                </text>
                <text className="country-map-tip-meta" textAnchor="middle" y="8">
                  {String(hoveredPin.event?.category || "unclassified").replaceAll("_", " ")} ·{" "}
                  {hoveredPin.event?.importance ?? "—"}/10
                </text>
              </g>
            ) : null}
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

