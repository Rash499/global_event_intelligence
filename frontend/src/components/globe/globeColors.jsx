export function getPolygonCapColor(
  country,
  events,
  selectedCountryCode,
  mode = "events",
  weather = []
) {
  const code = country.properties?.ISO_A2 || country.properties?.ISO_A2_E;

  if (selectedCountryCode && code === selectedCountryCode) {
    return "rgba(0, 200, 255, 0.55)";
  }

  if (mode === "weather") {
    const item = weather.find((entry) => entry.country_code === code);
    if (!item) return "rgba(40, 80, 110, 0.10)";

    const score = item.score || 0;
    if (score >= 81) return "rgba(255, 59, 92, 0.58)";
    if (score >= 61) return "rgba(255, 159, 67, 0.52)";
    if (score >= 41) return "rgba(255, 209, 102, 0.45)";
    if (score >= 21) return "rgba(86, 214, 161, 0.34)";
    return "rgba(54, 184, 255, 0.25)";
  }

  const countryEvents = events.filter((event) => event.country_code === code);
  if (!countryEvents.length) return "rgba(40, 80, 110, 0.12)";

  const maxImportance = Math.max(...countryEvents.map((event) => event.importance));

  if (maxImportance >= 8) return "rgba(255, 70, 90, 0.45)";
  if (maxImportance >= 6) return "rgba(255, 170, 50, 0.40)";
  return "rgba(60, 180, 255, 0.35)";
}

export const getPolygonSideColor = () => "rgba(20, 50, 70, 0.38)";
export const getPolygonStrokeColor = () => "rgba(150, 220, 255, 0.82)";

export function getPointColor(event) {
  if (event.importance >= 8) return "#ff3b5c";
  if (event.importance >= 6) return "#ffb020";
  return "#36b8ff";
}

export function getRingColor(event) {
  return event.importance >= 8 ? "#ff3b5c" : "#ffb020";
}

export function getPolygonLabel(country, mode = "events", weather = []) {
  const name = country.properties?.NAME || country.properties?.ADMIN || "Unknown";

  if (mode === "weather") {
    const code = country.properties?.ISO_A2 || country.properties?.ISO_A2_E;
    const item = weather.find((entry) => entry.country_code === code);

    if (!item) {
      return `<div style="background:#07111f;color:white;padding:8px 12px;border-radius:8px;font-family:Arial;"><strong>${name}</strong><br/><small>Weather data unavailable</small></div>`;
    }

    return `<div style="background:#07111f;color:white;padding:8px 12px;border-radius:8px;font-family:Arial;"><strong>${name}</strong><br/><small>${item.current?.weather_description || "Unknown"} · Severity ${Math.round(item.score || 0)}/100</small></div>`;
  }

  return `<div style="background:#07111f;color:white;padding:8px 12px;border-radius:8px;font-family:Arial;"><strong>${name}</strong><br/><small>Click to explore events</small></div>`;
}

export function getPointLabel(event) {
  return `<div style="background:#07111f;color:white;padding:10px 14px;border-radius:8px;font-family:Arial;max-width:280px;"><strong>${event.title}</strong><br/><small>${event.country || "Global"} · Importance ${event.importance}/10</small></div>`;
}
