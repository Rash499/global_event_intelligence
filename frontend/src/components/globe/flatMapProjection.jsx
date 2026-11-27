/**
 * Equirectangular projection for the flat (2D) world map.
 *
 * Deliberately the simplest honest world projection: longitude and latitude
 * map linearly onto the canvas, using the same bundled Natural Earth
 * GeoJSON as the 3D globe (which is pre-cut at the antimeridian, so no
 * wrap-around lines are drawn). Shapes distort toward the poles, as with
 * any flat world map — the globe remains the primary view.
 */

export const FLAT_VIEW_W = 1000;
export const FLAT_VIEW_H = 500;

export function projectEquirectangular(longitude, latitude) {
  const lon = Math.max(-180, Math.min(180, Number(longitude) || 0));
  const lat = Math.max(-90, Math.min(90, Number(latitude) || 0));
  return [
    Math.round((((lon + 180) / 360) * FLAT_VIEW_W) * 10) / 10,
    Math.round((((90 - lat) / 180) * FLAT_VIEW_H) * 10) / 10,
  ];
}

function collectRings(geometry) {
  if (!geometry || !geometry.coordinates) return [];
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

/** Build an SVG path `d` string for one GeoJSON feature. */
export function featurePath(feature) {
  const parts = [];
  for (const ring of collectRings(feature?.geometry)) {
    const points = (ring || []).filter(
      (point) => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])
    );
    if (points.length < 3) continue;
    parts.push(
      points
        .map((point, index) => {
          const [x, y] = projectEquirectangular(point[0], point[1]);
          return `${index === 0 ? "M" : "L"}${x},${y}`;
        })
        .join(" ") + " Z"
    );
  }
  return parts.join(" ");
}

export function countryCodeOf(feature) {
  const props = feature?.properties || {};
  const code = props.ISO_A2 || props.ISO_A2_E;
  return code && code !== "-99" ? code : null;
}

export function countryNameOf(feature) {
  const props = feature?.properties || {};
  return props.NAME || props.ADMIN || "Unknown";
}

/** Plain-text point label (the globe uses HTML tooltips; SVG uses <title>). */
export function pointPlainLabel(point) {
  if (point.is_cluster) {
    return `${point.cluster_count} events clustered in this area — marker is the average of reported locations`;
  }
  if (point.is_country_aggregate) {
    return `${point.title} — country-level aggregate, exact locations not reported`;
  }
  return `${point.title} — ${point.country || "Global"}`;
}
