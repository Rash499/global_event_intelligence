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

export {
  VIEW_W,
  VIEW_H,
  PAD,
  CLUSTER_TOLERANCE_DEG,
  MAX_RING_POINTS,
  MAX_PINS,
  SEVERITY_LEVELS,
  finite,
  severityLevel,
  severityColor,
  shortLabel,
  clamp,
  collectRings,
  validRing,
  ringBounds,
  lngGap,
  boundsGap,
  clusterRings,
  buildGrid,
  buildMap,
};
