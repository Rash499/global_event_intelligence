export function getPolygonCapColor(country, events, selectedCountryCode) {
  const code = country.properties?.ISO_A2 || country.properties?.ISO_A2_E;

  if (selectedCountryCode && code === selectedCountryCode) {
    return "rgba(0, 200, 255, 0.55)";
  }

  const countryEvents = events.filter((event) => event.country_code === code);

  if (!countryEvents.length) return "rgba(40, 80, 110, 0.12)";

  const maxImportance = Math.max(
    ...countryEvents.map((event) => event.importance)
  );

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

export function getPolygonLabel(country) {
  const name = country.properties?.NAME || country.properties?.ADMIN || "Unknown";

  return `<div style="background:#07111f;color:white;padding:8px 12px;border-radius:8px;font-family:Arial;"><strong>${name}</strong><br/><small>Click to explore events</small></div>`;
}

export function getPointLabel(event) {
  return `<div style="background:#07111f;color:white;padding:10px 14px;border-radius:8px;font-family:Arial;max-width:280px;"><strong>${event.title}</strong><br/><small>${event.country || "Global"} · Importance ${event.importance}/10</small></div>`;
}
