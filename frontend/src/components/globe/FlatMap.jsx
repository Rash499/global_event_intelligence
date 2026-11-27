import { useEffect, useMemo, useState } from "react";

import { loadWorldGeoJSON } from "../../services/worldGeoJson.jsx";
import { getPolygonCapColor, getPointColor } from "./globeColors";
import {
  FLAT_VIEW_H,
  FLAT_VIEW_W,
  countryCodeOf,
  countryNameOf,
  featurePath,
  pointPlainLabel,
  projectEquirectangular,
} from "./flatMapProjection.jsx";

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;

/**
 * Flat 2D world map — the worldmonitor dual-engine pattern's second surface.
 *
 * Renders the same data as the 3D globe from the same bundled GeoJSON:
 * country shading from `polygonEvents`, pins/clusters/country aggregates
 * from `events`, with identical click routing (MapView passes the same
 * handlers). Zoom is button/drag based; shapes are equirectangular and
 * distort toward the poles, which the view badge states.
 */
export default function FlatMap({
  mode = "events",
  events = [],
  polygonEvents,
  weather = [],
  onSelectEvent,
  onSelectCountry,
  selectedCountryCode,
}) {
  const [features, setFeatures] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const [view, setView] = useState({ scale: 1, tx: 0, ty: 0 });
  const [drag, setDrag] = useState(null);

  useEffect(() => {
    let cancelled = false;
    loadWorldGeoJSON()
      .then((geojson) => {
        if (!cancelled) setFeatures(geojson.features || []);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const shadingEvents = polygonEvents ?? events;
  const points = useMemo(
    () =>
      mode === "events"
        ? (events || []).filter(
            (event) => event.latitude !== null && event.longitude !== null
          )
        : [],
    [events, mode]
  );

  const zoomBy = (factor) => {
    setView((current) => {
      const scale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, current.scale * factor));
      // Keep the pan roughly stable when returning to the full view.
      return scale === 1 ? { scale: 1, tx: 0, ty: 0 } : { ...current, scale };
    });
  };

  const handlePointerDown = (event) => {
    if (view.scale === 1) return;
    setDrag({ x: event.clientX, y: event.clientY, tx: view.tx, ty: view.ty });
  };
  const handlePointerMove = (event) => {
    if (!drag) return;
    setView((current) => ({
      ...current,
      tx: drag.tx + (event.clientX - drag.x),
      ty: drag.ty + (event.clientY - drag.y),
    }));
  };
  const endDrag = () => setDrag(null);

  return (
    <div className="flatmap-stage" data-testid="flat-map">
      <svg
        viewBox={`0 0 ${FLAT_VIEW_W} ${FLAT_VIEW_H}`}
        className="flatmap-svg"
        role="img"
        aria-label="Flat world map of stored events"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <rect x="0" y="0" width={FLAT_VIEW_W} height={FLAT_VIEW_H} className="flatmap-ocean" />
        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          {features.map((feature, index) => {
            const code = countryCodeOf(feature);
            const selected = code && selectedCountryCode && code === selectedCountryCode;
            return (
              <path
                key={code || index}
                d={featurePath(feature)}
                fill={getPolygonCapColor(feature, shadingEvents, selectedCountryCode, mode, weather)}
                className={`flatmap-country${selected ? " is-selected" : ""}`}
                onClick={() => {
                  if (code) onSelectCountry?.({ code, name: countryNameOf(feature) });
                }}
              >
                <title>{countryNameOf(feature)}</title>
              </path>
            );
          })}
          {points.map((point) => {
            const [x, y] = projectEquirectangular(point.longitude, point.latitude);
            const radius = point.is_cluster
              ? 9
              : point.is_country_aggregate
                ? 8
                : 3.2 + Math.min(2.8, (point.importance || 0) * 0.3);
            return (
              <g
                key={point.id}
                className="flatmap-point"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectEvent?.(point);
                }}
              >
                <circle cx={x} cy={y} r={radius} fill={getPointColor(point)} />
                {(point.is_cluster || point.is_country_aggregate) && (
                  <text x={x} y={y + 3} className="flatmap-point-count">
                    {point.cluster_count ?? point.aggregate_count ?? ""}
                  </text>
                )}
                <title>{pointPlainLabel(point)}</title>
              </g>
            );
          })}
        </g>
      </svg>
      <div className="flatmap-controls">
        <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.4)}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.4)}>−</button>
        <button
          type="button"
          aria-label="Reset view"
          onClick={() => setView({ scale: 1, tx: 0, ty: 0 })}
        >
          ⟲
        </button>
      </div>
      <div className="flatmap-badge" aria-hidden="true">
        {loadError
          ? "Country outlines unavailable"
          : features.length
            ? "Flat map · equirectangular (polar distortion) · drag to pan when zoomed"
            : "Loading country outlines…"}
      </div>
    </div>
  );
}
