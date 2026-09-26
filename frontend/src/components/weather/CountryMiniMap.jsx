import { useEffect, useMemo, useRef, useState } from "react";
import { loadWorldGeoJSON } from "../../services/worldGeoJson.jsx";

const VIEW_W = 480;
const VIEW_H = 320;
const PAD = 14;

function collectRings(geometry) {
  if (!geometry || !geometry.coordinates) return [];
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

function ringsForCountry(features, countryCode, countryName) {
  const code = (countryCode || "").toUpperCase();
  const name = (countryName || "").toLowerCase();
  const matched = (features || []).filter((feature) => {
    const props = feature.properties || {};
    const codes = [props.ISO_A2, props.ISO_A2_E, props.ISO_A2_EH, props.ISO_A3]
      .filter((v) => typeof v === "string")
      .map((v) => v.toUpperCase());
    if (code && codes.includes(code)) return true;
    if (name) {
      const names = [props.NAME, props.ADMIN, props.NAME_LONG]
        .filter((v) => typeof v === "string")
        .map((v) => v.toLowerCase());
      if (names.includes(name)) return true;
    }
    return false;
  });
  return matched.flatMap((f) => collectRings(f.geometry));
}

function buildCountryMap(rings, marker) {
  const points = [];
  rings.forEach((ring) => {
    (ring || []).forEach((p) => {
      if (Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])) points.push(p);
    });
  });
  const refLng = Number.isFinite(marker?.lng) ? marker.lng : 0;
  const shift = (lng) => {
    let a = lng;
    while (a - refLng > 180) a -= 360;
    while (a - refLng < -180) a += 360;
    return a;
  };
  const shifted = points.map(([lng, lat]) => [shift(lng), lat]);
  const lons = shifted.map((p) => p[0]);
  const lats = shifted.map((p) => p[1]);
  if (marker && Number.isFinite(marker.lng) && Number.isFinite(marker.lat)) {
    lons.push(marker.lng);
    lats.push(marker.lat);
  }
  if (!lons.length) return null;
  let minLng = Math.min(...lons);
  let maxLng = Math.max(...lons);
  let minLat = Math.min(...lats);
  let maxLat = Math.max(...lats);
  if (maxLng - minLng < 0.6) { minLng -= 0.3; maxLng += 0.3; }
  if (maxLat - minLat < 0.6) { minLat -= 0.3; maxLat += 0.3; }
  const spanLng = maxLng - minLng;
  const spanLat = maxLat - minLat;
  const scale = Math.min((VIEW_W - PAD * 2) / spanLng, (VIEW_H - PAD * 2) / spanLat);
  const offX = (VIEW_W - spanLng * scale) / 2;
  const offY = (VIEW_H - spanLat * scale) / 2;
  const project = ([lng, lat]) => [offX + (shift(lng) - minLng) * scale, offY + (maxLat - lat) * scale];
  const path = rings.map((ring) => {
    const pts = (ring || [])
      .filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]))
      .map((p) => project(p));
    if (!pts.length) return "";
    const [first, ...rest] = pts;
    return `M ${first[0].toFixed(1)} ${first[1].toFixed(1)}` + rest.map((p) => ` L ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join("") + " Z";
  }).filter(Boolean).join(" ");
  const grid = [];
  const lngStep = spanLng > 60 ? 10 : spanLng > 20 ? 5 : 2;
  const latStep = spanLat > 40 ? 10 : spanLat > 12 ? 5 : 2;
  for (let lng = Math.ceil(minLng / lngStep) * lngStep; lng <= maxLng; lng += lngStep) {
    const [x1, y1] = project([lng, minLat]);
    const [x2, y2] = project([lng, maxLat]);
    grid.push({ x1, y1, x2, y2, key: `lng-${lng.toFixed(1)}` });
  }
  for (let lat = Math.ceil(minLat / latStep) * latStep; lat <= maxLat; lat += latStep) {
    const [x1, y1] = project([minLng, lat]);
    const [x2, y2] = project([maxLng, lat]);
    grid.push({ x1, y1, x2, y2, key: `lat-${lat.toFixed(1)}` });
  }
  const markerXY = marker && Number.isFinite(marker.lng) && Number.isFinite(marker.lat) ? project([marker.lng, marker.lat]) : null;
  return { path, grid, markerXY, minLng, maxLng, minLat, maxLat };
}

const severityHex = (s = "normal") => {
  if (String(s).toLowerCase() === "extreme") return "#ff5d7a";
  if (String(s).toLowerCase() === "high") return "#ff9f43";
  if (String(s).toLowerCase() === "moderate") return "#ffd166";
  if (String(s).toLowerCase() === "low") return "#56d6a1";
  return "#36b8ff";
}

export default function CountryMiniMap({ weather }) {
  const [features, setFeatures] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [hover, setHover] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pin, setPin] = useState(null);
  const svgRef = useRef(null);
  const code = weather?.country_code;
  const name = weather?.country;
  useEffect(() => {
    let on = true;
    loadWorldGeoJSON().then((d) => { if (on) setFeatures(d.features || []); }).catch((e) => { if (on) setLoadError(e?.message || "Outline unavailable."); });
    return () => { on = false; };
  }, []);
  useEffect(() => { setZoom(1); setPin(null); }, [code]);
  const rings = useMemo(() => ringsForCountry(features || [], code, name), [features, code, name]);
  const marker = useMemo(() => {
    if (!Number.isFinite(weather?.latitude) || !Number.isFinite(weather?.longitude)) return null;
    return { lat: weather.latitude, lng: weather.longitude };
  }, [weather]);
  const map = useMemo(() => buildCountryMap(rings, marker), [rings, marker]);
  const accent = severityHex(weather?.severity);
  const zLabel = zoom === 1 ? "Fit" : `${zoom.toFixed(1)}x`;
  const onClick = (e) => {
    if (!svgRef.current || !map) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * VIEW_W;
    const y = ((e.clientY - r.top) / r.height) * VIEW_H;
    const sLng = map.maxLng - map.minLng;
    const sLat = map.maxLat - map.minLat;
    const sc = Math.min((VIEW_W - PAD * 2) / sLng, (VIEW_H - PAD * 2) / sLat);
    const ox = (VIEW_W - sLng * sc) / 2;
    const oy = (VIEW_H - sLat * sc) / 2;
    const lng = map.minLng + (x - ox) / sc;
    const lat = map.maxLat - (y - oy) / sc;
    const ok = lng >= map.minLng - 5 && lng <= map.maxLng + 5 && lat >= map.minLat - 5 && lat <= map.maxLat + 5;
    setPin(ok ? { x, y, lng, lat } : null);
  };
  return (
    <div className={`mini-map-card ${hover ? "is-hover" : ""}`}>
      <div className="mini-map-header">
        <div>
          <span className="section-eyebrow">COUNTRY FOCUS</span>
          <h3>{name || "Unknown"} <span className="mini-map-code">{code || ""}</span></h3>
        </div>
        <div className="mini-map-actions">
          <span className="mini-map-zoom-label">{zLabel}</span>
          <button type="button" className="mini-map-btn" disabled={zoom <= 1} onClick={() => setZoom((v) => Math.max(1, +(v - 0.5).toFixed(1)))}>-</button>
          <button type="button" className="mini-map-btn" disabled={zoom >= 4} onClick={() => setZoom((v) => Math.min(4, +(v + 0.5).toFixed(1)))}>+</button>
          <button type="button" className="mini-map-btn mini-map-reset" disabled={zoom === 1 && !pin} onClick={() => { setZoom(1); setPin(null); }}>Reset</button>
        </div>
      </div>
      <div className="mini-map-canvas" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onClick={onClick} role="img" aria-label={name ? `Mini map of ${name}` : "Mini map"}>
        {loadError || !map || !map.path ? (
          <div className="mini-map-fallback">{loadError || "Outline unavailable."}</div>
        ) : (
          <svg ref={svgRef} className="mini-map-svg" viewBox="0 0 480 320" preserveAspectRatio="xMidYMid meet">
            <defs>
              <radialGradient id="mini-map-glow" cx="50%" cy="45%" r="75%">
                <stop offset="0%" stopColor={accent} stopOpacity="0.22" />
                <stop offset="100%" stopColor={accent} stopOpacity="0" />
              </radialGradient>
              <linearGradient id="mini-map-fill" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor={accent} stopOpacity="0.42" />
                <stop offset="100%" stopColor={accent} stopOpacity="0.16" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="480" height="320" fill="url(#mini-map-glow)" />
            <g className="mini-map-zoom-layer" style={{ transform: `translate(240px, 160px) scale(${zoom}) translate(-240px, -160px)` }}>
              {map.grid.map((l) => (<line key={l.key} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} className="mini-map-grid" />))}
              <path d={map.path} className="mini-map-country" fill="url(#mini-map-fill)" style={{ stroke: accent }} />

              {map.markerXY && (
                <g className="mini-map-marker" style={{ color: accent }}>
                  <circle cx={map.markerXY[0]} cy={map.markerXY[1]} r="14" className="mini-map-pulse" />
                  <circle cx={map.markerXY[0]} cy={map.markerXY[1]} r="5" className="mini-map-dot" />
                  <circle cx={map.markerXY[0]} cy={map.markerXY[1]} r="2" className="mini-map-core" />
                </g>
              )}
              {pin && (
                <g className="mini-map-pin" transform={`translate(${pin.x}, ${pin.y})`}>
                  <line x1="0" y1="0" x2="0" y2="-16" />
                  <circle cx="0" cy="-19" r="6" />
                  <circle cx="0" cy="-19" r="2" className="mini-map-core" />
                </g>
              )}
            </g>
          </svg>
        )}
        <div className="mini-map-legend" aria-hidden="true">
          <span className="mini-map-legend-dot" style={{ background: accent }} />
          {weather?.severity || "Normal"} - {Math.round(weather?.score || 0)}/100
        </div>
      </div>
      <div className="mini-map-footer">
        {marker ? (<><span>Pin {marker.lat.toFixed(2)}, {marker.lng.toFixed(2)}</span>{pin && (<span className="mini-map-pin-readout">Your pin {pin.lat.toFixed(2)}, {pin.lng.toFixed(2)}</span>)}</>) : (<span>No coordinates.</span>)}
        {weather?.timezone && <span>{weather.timezone}</span>}
      </div>
    </div>
  );
}