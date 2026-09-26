import { useEffect, useMemo, useRef, useState } from "react";
import {
  loadWorldGeoJSON,
  matchCountryFeatures,
  normalizeCountryCode,
} from "../../services/worldGeoJson.jsx";
import { CAPITALS, MAJOR_CITIES } from "../../services/countryCities.jsx";
import { getGlobalWeather } from "../../services/api.jsx";

const VIEW_W = 480;
const VIEW_H = 320;
const PAD = 16;
const MAX_CITY_SAMPLES = 5;
const CITY_CACHE = new Map();

function collectRings(geometry) {
  if (!geometry || !geometry.coordinates) return [];
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

function finite(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function severityHex(severity = "normal") {
  const value = String(severity || "normal").toLowerCase();
  if (value === "extreme") return "#ff5d7a";
  if (value === "high") return "#ff9f43";
  if (value === "moderate") return "#ffd166";
  if (value === "low") return "#56d6a1";
  return "#36b8ff";
}

function iconFor(description = "") {
  const text = String(description || "").toLowerCase();
  if (text.includes("thunder")) return "⛈️";
  if (text.includes("snow") || text.includes("blizzard")) return "❄️";
  if (text.includes("rain") || text.includes("drizzle") || text.includes("shower")) return "🌧️";
  if (text.includes("fog") || text.includes("mist") || text.includes("haze")) return "🌫️";
  if (text.includes("cloud") || text.includes("overcast")) return "☁️";
  if (text.includes("clear") || text.includes("sun")) return "☀️";
  return "🌤️";
}

function tempText(value) {
  const n = finite(value);
  return n === null ? "—" : `${Math.round(n)}°C`;
}

function shortName(value, max = 12) {
  const text = String(value || "").trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

// The weather endpoint returns { locations: [...] }; accept both shapes so the
// mini map keeps working if the payload is ever unwrapped upstream.
function readLocations(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.locations)) return payload.locations;
  return [];
}
function buildCountryMap(rings, marker, extras = []) {
  const points = [];
  rings.forEach((ring) => {
    (ring || []).forEach((point) => {
      if (Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])) {
        points.push(point);
      }
    });
  });
  const refLng = Number.isFinite(marker?.lng)
    ? marker.lng
    : (Number.isFinite(extras?.[0]?.lng) ? extras[0].lng : 0);
  // Unwrap longitudes relative to the reference point so antimeridian countries
  // (Russia, Fiji, USA/Aleutians) render as one continuous shape.
  const shift = (lng) => {
    let value = lng;
    while (value - refLng > 180) value -= 360;
    while (value - refLng < -180) value += 360;
    return value;
  };
  const all = points.map(([lng, lat]) => [shift(lng), lat]);
  if (Number.isFinite(marker?.lng) && Number.isFinite(marker?.lat)) {
    all.push([marker.lng, marker.lat]);
  }
  extras.forEach((extra) => {
    if (Number.isFinite(extra?.lng) && Number.isFinite(extra?.lat)) {
      all.push([shift(extra.lng), extra.lat]);
    }
  });
  if (!all.length) return null;

  const lons = all.map((point) => point[0]);
  const lats = all.map((point) => point[1]);
  let minLng = Math.min(...lons);
  let maxLng = Math.max(...lons);
  let minLat = Math.min(...lats);
  let maxLat = Math.max(...lats);

  // No outline matched: fall back to a sampling box around the known points so
  // the panel still renders something meaningful instead of an empty canvas.
  const fallback = rings.length === 0;
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
  const unproject = ([x, y]) => [
    minLng + (x - offX) / scale,
    maxLat - (y - offY) / scale,
  ];

  const path = rings
    .map((ring) => {
      const coords = (ring || [])
        .filter((point) => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1]))
        .map((point) => project(point));
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

  const grid = [];
  const lngStep = spanLng > 60 ? 10 : spanLng > 20 ? 5 : 2;
  const latStep = spanLat > 40 ? 10 : spanLat > 12 ? 5 : 2;
  for (let lng = Math.ceil(minLng / lngStep) * lngStep; lng <= maxLng; lng += lngStep) {
    const [x1, y1] = project([lng, minLat]);
    const [x2, y2] = project([lng, maxLat]);
    grid.push({ key: `lng-${lng.toFixed(1)}`, x1, y1, x2, y2, label: `${lng.toFixed(0)}°` });
  }
  for (let lat = Math.ceil(minLat / latStep) * latStep; lat <= maxLat; lat += latStep) {
    const [x1, y1] = project([minLng, lat]);
    const [x2, y2] = project([maxLng, lat]);
    grid.push({ key: `lat-${lat.toFixed(1)}`, x1, y1, x2, y2, label: `${lat.toFixed(0)}°` });
  }

  const markerXY = Number.isFinite(marker?.lng) && Number.isFinite(marker?.lat)
    ? project([marker.lng, marker.lat])
    : null;
  const [boxX1, boxY1] = project([minLng, maxLat]);
  const [boxX2, boxY2] = project([maxLng, minLat]);

  return {
    path,
    grid,
    markerXY,
    minLng,
    maxLng,
    minLat,
    maxLat,
    project,
    unproject,
    spanLng,
    spanLat,
    fallback,
    box: { x: boxX1, y: boxY1, width: boxX2 - boxX1, height: boxY2 - boxY1 },
  };
}

function ringBounds(ring) {
  const valid = (ring || []).filter(
    (point) => Array.isArray(point) && Number.isFinite(point[0]) && Number.isFinite(point[1])
  );
  if (!valid.length) return null;
  const lngs = valid.map((point) => point[0]);
  const lats = valid.map((point) => point[1]);
  return {
    ring: valid,
    points: valid.length,
    minLng: Math.min(...lngs),
    maxLng: Math.max(...lngs),
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
  };
}

// Wrap-aware gap between two longitude ranges so antimeridian neighbours
// (Fiji, Russia, Aleutians) still count as touching.
function lngGap(a, b) {
  let best = Number.POSITIVE_INFINITY;
  [-360, 0, 360].forEach((offset) => {
    const gap = Math.max(a.minLng + offset - b.maxLng, b.minLng - (a.maxLng + offset), 0);
    if (gap < best) best = gap;
  });
  return best;
}

function clusterRings(rings, anchors = [], tolerance = 6) {
  const items = (rings || []).map(ringBounds).filter(Boolean);
  if (items.length < 2) return { rings: items.map((item) => item.ring), total: items.length, dropped: 0 };

  const parent = items.map((_, index) => index);
  const find = (index) => (parent[index] === index ? index : (parent[index] = find(parent[index])));
  const union = (a, b) => {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent[rootB] = rootA;
  };
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const latGap = Math.max(items[i].minLat - items[j].maxLat, items[j].minLat - items[i].maxLat, 0);
      if (latGap <= tolerance && lngGap(items[i], items[j]) <= tolerance) union(i, j);
    }
  }

  const groups = new Map();
  items.forEach((item, index) => {
    const root = find(index);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push({ item, index });
  });
  if (groups.size === 1) return { rings: items.map((item) => item.ring), total: items.length, dropped: 0 };

  const anchorList = (anchors || []).filter(
    (anchor) => Number.isFinite(anchor?.lng) && Number.isFinite(anchor?.lat)
  );
  const containsAnchor = (group) =>
    anchorList.some((anchor) =>
      group.some(({ item }) => {
        const shifted = lngGap(
          { minLng: anchor.lng, maxLng: anchor.lng },
          item
        ) <= 0 && anchor.lat >= item.minLat - 1 && anchor.lat <= item.maxLat + 1;
        return shifted;
      })
    );

  let best = null;
  for (const group of groups.values()) {
    const flag = containsAnchor(group) ? 1 : 0;
    const total = group.reduce((sum, entry) => sum + entry.item.points, 0);
    const score = flag * 1e9 + total;
    if (!best || score > best.score) best = { score, group };
  }
  return {
    rings: best.group.map((entry) => entry.item.ring),
    total: items.length,
    dropped: items.length - best.group.length,
  };
}

export default function CountryMiniMap({ weather }) {
  const [features, setFeatures] = useState(null);
  const [outlineState, setOutlineState] = useState("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [pin, setPin] = useState(null);
  const [showCities, setShowCities] = useState(true);
  const [hoveredCity, setHoveredCity] = useState(null);
  const [activeCity, setActiveCity] = useState(null);
  const [cities, setCities] = useState([]);
  const [citiesState, setCitiesState] = useState("idle");
  const svgRef = useRef(null);

  const code = normalizeCountryCode(weather?.country_code) || "";
  const name = weather?.country || "";
  const scopeKey = `${code}|${name}|${finite(weather?.latitude) ?? ""}|${finite(weather?.longitude) ?? ""}`;

  useEffect(() => {
    let alive = true;
    setOutlineState("loading");
    loadWorldGeoJSON()
      .then((data) => {
        if (!alive) return;
        setFeatures(data?.features || []);
        setOutlineState("ready");
      })
      .catch(() => {
        if (!alive) return;
        setFeatures([]);
        setOutlineState("error");
      });
    return () => { alive = false; };
  }, [reloadKey]);

  useEffect(() => {
    setZoom(1);
    setPin(null);
    setActiveCity(null);
    setHoveredCity(null);
  }, [scopeKey]);

  const matches = useMemo(
    () => (features ? matchCountryFeatures(features, code, name) : []),
    [features, code, name]
  );

  const marker = useMemo(() => {
    const lat = finite(weather?.latitude);
    const lng = finite(weather?.longitude);
    return lat === null || lng === null ? null : { lat, lng };
  }, [weather?.latitude, weather?.longitude]);

  const cityPoints = useMemo(() => {
    if (!code) return [];
    const capital = CAPITALS[code];
    const majors = MAJOR_CITIES[code] || [];
    const list = [];
    const seen = new Set();
    const push = (city, lat, lng, isCapital) => {
      const la = finite(lat);
      const ln = finite(lng);
      if (la === null || ln === null) return;
      const key = `${la.toFixed(1)}:${ln.toFixed(1)}`;
      if (seen.has(key)) return;
      seen.add(key);
      list.push({ city: String(city), lat: la, lng: ln, capital: isCapital });
    };
    if (capital) push(capital[0], capital[1], capital[2], true);
    majors.forEach((entry) => {
      if (Array.isArray(entry)) push(entry[0], entry[1], entry[2], false);
    });
    return list.slice(0, MAX_CITY_SAMPLES);
  }, [code]);



  const shapeInfo = useMemo(() => {
    const raw = matches.flatMap((match) => collectRings(match.feature?.geometry));
    const anchors = marker ? [marker, ...cityPoints] : cityPoints;
    return clusterRings(raw, anchors);
  }, [matches, marker, cityPoints]);

  const map = useMemo(
    () => buildCountryMap(shapeInfo.rings, marker, cityPoints),
    [shapeInfo, marker, cityPoints]
  );

  const cityKey = cityPoints.map((city) => city.city).join("|");

  useEffect(() => {
    if (!code || !cityPoints.length) {
      setCities([]);
      setCitiesState("empty");
      return undefined;
    }
    const cacheKey = `${code}|${cityKey}`;
    const cached = CITY_CACHE.get(cacheKey);
    if (cached) {
      setCities(cached);
      setCitiesState("ready");
      return undefined;
    }
    let alive = true;
    setCities(cityPoints.map((city) => ({ ...city, weather: null })));
    setCitiesState("loading");
    getGlobalWeather(
      cityPoints.map((city) => ({
        country_code: code,
        country: `${city.city}${name ? `, ${name}` : ""}`.slice(0, 120),
        latitude: city.lat,
        longitude: city.lng,
      }))
    )
      .then((payload) => {
        if (!alive) return;
        const rows = readLocations(payload);
        const merged = cityPoints.map((city, index) => ({ ...city, weather: rows[index] || null }));
        CITY_CACHE.set(cacheKey, merged);
        setCities(merged);
        setCitiesState(rows.length ? "ready" : "error");
      })
      .catch(() => {
        if (!alive) return;
        setCities(cityPoints.map((city) => ({ ...city, weather: null })));
        setCitiesState("error");
      });
    return () => { alive = false; };
  }, [code, cityKey, cityPoints, name]);

  const dots = useMemo(() => {
    if (!showCities || !map) return [];
    return cities.map((city) => {
      const xy = map.project([city.lng, city.lat]);
      const x = xy?.[0];
      const y = xy?.[1];
      const severity = city.weather?.severity || "normal";
      return {
        ...city,
        x: Number.isFinite(x) ? x : VIEW_W / 2,
        y: Number.isFinite(y) ? y : VIEW_H / 2,
        severity,
        color: severityHex(severity),
        onMap:
          Number.isFinite(x) &&
          Number.isFinite(y) &&
          x >= -12 && x <= VIEW_W + 12 && y >= -12 && y <= VIEW_H + 12,
      };
    });
  }, [cities, map, showCities]);

  const accent = severityHex(weather?.severity);
  const plotted = dots.filter((dot) => dot.onMap).length;
  const selected = activeCity ? dots.find((dot) => dot.city === activeCity) || null : null;
  const hovered = hoveredCity ? dots.find((dot) => dot.city === hoveredCity) || null : null;
  const focusCity = hovered || selected;
  const active = selected;

  const outlineLabel =
    outlineState === "error"
      ? "outline unavailable · sampling box"
      : outlineState === "loading"
        ? "loading outline…"
        : matches.length
          ? `${shapeInfo.rings.length}/${shapeInfo.total} shape${shapeInfo.total > 1 ? "s" : ""} · ${matches[0].reason}`
          : "no ISO match · sampling box";

  const cityNote =
    citiesState === "loading"
      ? "fetching live city weather…"
      : citiesState === "empty"
        ? "no registered city samples"
        : `${plotted} of ${cities.length} plotted${map?.fallback ? " · sampling box" : ""}`;

  const toBase = (x, y) => [
    VIEW_W / 2 + (x - VIEW_W / 2) / zoom,
    VIEW_H / 2 + (y - VIEW_H / 2) / zoom,
  ];

  const onMapClick = (event) => {
    if (!svgRef.current || !map) return;
    if (event.target?.closest?.(".city-dot")) return;
    const rect = svgRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = ((event.clientX - rect.left) / rect.width) * VIEW_W;
    const y = ((event.clientY - rect.top) / rect.height) * VIEW_H;
    const [baseX, baseY] = toBase(x, y);
    const [lng, lat] = map.unproject([baseX, baseY]);
    const padLng = map.spanLng * 0.2 + 0.2;
    const padLat = map.spanLat * 0.2 + 0.2;
    const inside =
      lng >= map.minLng - padLng &&
      lng <= map.maxLng + padLng &&
      lat >= map.minLat - padLat &&
      lat <= map.maxLat + padLat;
    setPin(inside ? { x: baseX, y: baseY, lng, lat } : null);
  };

  const toggleCity = (city) => {
    setActiveCity((current) => (current === city ? null : city));
  };

  return (
    <div className="weather-section mini-map-panel">
      <div className="weather-section-heading">
        <div>
          <span className="section-eyebrow">GEOGRAPHY CHECK</span>
          <h3>Country mini map</h3>
        </div>
        <div className="mini-map-controls">
          <button
            type="button"
            className={`ghost-btn tiny ${showCities ? "on" : ""}`}
            onClick={() => setShowCities((value) => !value)}
          >
            {showCities ? "Cities on" : "Cities off"}
          </button>
          <button
            type="button"
            className="ghost-btn tiny"
            aria-label="Zoom in"
            onClick={() => setZoom((value) => Math.min(6, Number((value + 0.5).toFixed(1))))}
          >
            +
          </button>
          <button
            type="button"
            className="ghost-btn tiny"
            aria-label="Zoom out"
            onClick={() => setZoom((value) => Math.max(1, Number((value - 0.5).toFixed(1))))}
          >
            −
          </button>
          <button
            type="button"
            className="ghost-btn tiny"
            aria-label="Reset view"
            onClick={() => { setZoom(1); setPin(null); }}
          >
            Reset
          </button>
        </div>
      </div>
      <div className="mini-map-canvas">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className={`mini-map-svg ${zoom > 1.05 ? "is-zoomed" : ""}`}
          role="img"
          aria-label={`Map of ${name || code || "selected area"}`}
          onClick={onMapClick}
        >
          <defs>
            <linearGradient id="miniMapFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity="0.34" />
              <stop offset="100%" stopColor={accent} stopOpacity="0.08" />
            </linearGradient>
            <radialGradient id="miniMapGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor={accent} stopOpacity="0.3" />
              <stop offset="100%" stopColor={accent} stopOpacity="0" />
            </radialGradient>
          </defs>
          <g
            transform={`translate(${VIEW_W / 2} ${VIEW_H / 2}) scale(${zoom}) translate(${-VIEW_W / 2} ${-VIEW_H / 2})`}
          >
            <rect x="0" y="0" width={VIEW_W} height={VIEW_H} className="mini-map-ocean" />
            {map
              ? map.grid.map((line) => (
                  <line
                    key={line.key}
                    x1={line.x1}
                    y1={line.y1}
                    x2={line.x2}
                    y2={line.y2}
                    className="mini-map-grid-line"
                  />
                ))
              : null}
            {map?.fallback ? (
              <rect
                x={map.box.x}
                y={map.box.y}
                width={map.box.width}
                height={map.box.height}
                className="mini-map-fallback-box"
              />
            ) : null}
            {map?.path ? (
              <path d={map.path} className="mini-map-land" fill="url(#miniMapFill)" stroke={accent} />
            ) : null}
            {map?.markerXY ? (
              <g className="mini-map-marker" transform={`translate(${map.markerXY[0]} ${map.markerXY[1]})`}>
                <circle r="18" fill="url(#miniMapGlow)" />
                <circle r="6.5" className="mini-map-marker-ring" stroke={accent} />
                <circle r="2.6" fill="#ffffff" />
              </g>
            ) : null}
            {dots.filter((dot) => dot.onMap).map((dot) => (
              <g
                key={`${dot.city}-${dot.lat}`}
                className={`city-dot ${dot.capital ? "is-capital" : ""} ${selected?.city === dot.city ? "is-active" : ""} ${hoveredCity === dot.city ? "is-hover" : ""}`}
                transform={`translate(${dot.x} ${dot.y})`}
                onClick={(event) => { event.stopPropagation(); toggleCity(dot.city); }}
                onMouseEnter={() => setHoveredCity(dot.city)}
                onMouseLeave={() => setHoveredCity((value) => (value === dot.city ? null : value))}
              >
                <circle r={dot.capital ? 9 : 7} className="city-dot-halo" fill={dot.color} />
                <circle r={dot.capital ? 3.6 : 2.8} fill={dot.color} stroke="#07131f" strokeWidth="1" />
                {dot.capital ? <text className="city-dot-star" y="-11" textAnchor="middle">★</text> : null}
                {dot.capital || selected?.city === dot.city || hoveredCity === dot.city ? (
                  <text className="city-dot-label" x="9" y="-5">
                    {shortName(dot.city)}
                    {dot.weather ? ` ${tempText(dot.weather.current?.temperature_2m)}` : ""}
                  </text>
                ) : null}
              </g>
            ))}
            {pin ? (
              <g transform={`translate(${pin.x} ${pin.y})`}>
                <circle r="4" className="mini-map-pin" />
                <text className="mini-map-pin-label" y="-9" textAnchor="middle">
                  {pin.lat.toFixed(1)}°, {pin.lng.toFixed(1)}°
                </text>
              </g>
            ) : null}
          </g>
        </svg>
        <div className="mini-map-overlay">
          <span className={`chip ghost tiny ${outlineState === "error" ? "warn" : ""}`}>{outlineLabel}</span>
          {focusCity ? (
            <span className="chip ghost tiny">
              {iconFor(focusCity.weather?.current?.weather_description)} {focusCity.city}
              {focusCity.weather ? ` · ${tempText(focusCity.weather.current?.temperature_2m)}` : " · no sample"}
            </span>
          ) : null}
          {pin ? <span className="chip ghost tiny">{pin.lat.toFixed(2)}°, {pin.lng.toFixed(2)}°</span> : null}
        </div>
      </div>
      <div className="mini-map-cities">
        <div className="mini-map-cities-head">
          <span className="section-eyebrow">CITY SAMPLES</span>
          <span className="mini-map-note">{cityNote}</span>
        </div>
        {citiesState === "empty" ? (
          <p className="mini-map-empty">
            No city samples registered for this area — showing the reporting point only.
          </p>
        ) : null}
        {citiesState === "error" ? (
          <p className="mini-map-empty">
            Live city weather is unavailable right now.
            <button
              type="button"
              className="ghost-btn tiny"
              onClick={() => {
                CITY_CACHE.delete(`${code}|${cityKey}`);
                setCitiesState("idle");
                setReloadKey((value) => value + 1);
              }}
            >
              Retry
            </button>
          </p>
        ) : null}
        {cities.length ? (
          <ul className="city-weather-list">
            {cities.map((city) => {
              const current = city.weather?.current || {};
              const isActive = activeCity === city.city;
              return (
                <li key={`${city.city}-${city.lat}`}>
                  <button
                    type="button"
                    className={`city-weather-row ${isActive ? "is-active" : ""} ${hoveredCity === city.city ? "is-hover" : ""}`}
                    onClick={() => toggleCity(city.city)}
                    onMouseEnter={() => setHoveredCity(city.city)}
                    onMouseLeave={() => setHoveredCity((value) => (value === city.city ? null : value))}
                  >
                    <span className="city-weather-name">
                      {city.capital ? <em className="city-badge">capital</em> : null}
                      {city.city}
                    </span>
                    <span className="city-weather-icon" aria-hidden="true">{iconFor(current.weather_description)}</span>
                    <span className="city-weather-temp">
                      {city.weather ? tempText(current.temperature_2m) : citiesState === "loading" ? "…" : "—"}
                    </span>
                    <span className={`city-weather-chip ${String(city.weather?.severity || "normal").toLowerCase()}`}>
                      {city.weather ? `${Math.round(Number(city.weather.score) || 0)}` : "—"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
        {active ? (
          <div className="city-detail">
            <div className="city-detail-head">
              <strong>{iconFor(active.weather?.current?.weather_description)} {active.city}</strong>
              <span className="city-detail-coords">{active.lat.toFixed(2)}°, {active.lng.toFixed(2)}°</span>
            </div>
            {active.weather ? (
              <>
                <p className="city-detail-sub">
                  {active.weather.current?.weather_description || "Current"} ·{" "}
                  {tempText(active.weather.current?.temperature_2m)} · feels{" "}
                  {tempText(active.weather.current?.apparent_temperature)}
                </p>
                <div className="city-detail-metrics">
                  <span>Precip<strong>{Number(active.weather.current?.precipitation || 0).toFixed(1)} mm</strong></span>
                  <span>Chance<strong>{Math.round(Number(active.weather.current?.precipitation_probability || 0))}%</strong></span>
                  <span>Wind<strong>{Math.round(Number(active.weather.current?.wind_speed_10m || 0))} km/h</strong></span>
                  <span>Gusts<strong>{Math.round(Number(active.weather.current?.wind_gusts_10m || 0))} km/h</strong></span>
                  <span>Score<strong>{Math.round(Number(active.weather.score) || 0)}/100</strong></span>
                  <span>Peak<strong>{Math.round(Number(active.weather.forecast_score) || 0)}/100</strong></span>
                </div>
                <p className="city-detail-foot">
                  <em className={`city-weather-chip ${String(active.weather.severity || "normal").toLowerCase()}`}>
                    {active.weather.severity}
                  </em>
                  {active.weather.timezone ? <span>{active.weather.timezone}</span> : null}
                  <span>
                    {active.capital ? "Capital sample" : "Metro sample"} · Open-Meteo
                  </span>
                </p>
              </>
            ) : (
              <p className="mini-map-empty">
                {citiesState === "loading" ? "Loading this city's live sample…" : "No live sample for this city."}
              </p>
            )}
          </div>
        ) : null}
        <p className="mini-map-foot">
          Click the map to drop a coordinate pin, or pick a city to sync it with the list above.
          {weather?.timezone ? ` Local time zone: ${weather.timezone}.` : ""}
        </p>
      </div>
    </div>
  );
}

