import { useEffect } from "react";

function pointColor(item) {
  if (item.score >= 81) return "#ff3b5c";
  if (item.score >= 61) return "#ff9f43";
  if (item.score >= 41) return "#ffd166";
  if (item.score >= 21) return "#56d6a1";
  return "#36b8ff";
}

function pointLabel(item) {
  return `<div style="background:#07111f;color:white;padding:10px 14px;border-radius:8px;font-family:Arial;max-width:300px;"><strong>${item.country || item.country_code || "Weather area"}</strong><br/><small>${item.current?.weather_description || "Unknown"} · Severity ${Math.round(item.score || 0)}/100</small></div>`;
}

export function useWeatherPoints({ globeRef, weather, enabled, onSelectWeather }) {
  useEffect(() => {
    if (!globeRef.current || !enabled) return;

    const valid = weather.filter(
      (item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude)
    );

    globeRef.current
      .pointsData(valid)
      .pointLat("latitude")
      .pointLng("longitude")
      .pointAltitude((item) => 0.02 + Math.min(0.055, (item.score || 0) / 1800))
      .pointRadius((item) => 0.25 + Math.min(0.75, (item.score || 0) / 100))
      .pointResolution(16)
      .pointColor(pointColor)
      .pointLabel(pointLabel)
      .onPointClick((item) => onSelectWeather(item));

    globeRef.current
      .ringsData(valid.filter((item) => item.score >= 61))
      .ringLat("latitude")
      .ringLng("longitude")
      .ringColor(pointColor)
      .ringMaxRadius((item) => 1.5 + (item.score || 0) * 0.035)
      .ringPropagationSpeed(1.2)
      .ringRepeatPeriod(1600);
  }, [globeRef, weather, enabled, onSelectWeather]);
}
