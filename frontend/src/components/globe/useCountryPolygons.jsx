import { useEffect, useRef } from "react";
import {
  getPolygonCapColor,
  getPolygonSideColor,
  getPolygonLabel,
} from "./globeColors";
import { loadWorldGeoJSON } from "../../services/worldGeoJson.jsx";

export function useCountryPolygons({
  globeRef,
  events,
  weather,
  mode,
  onSelectCountry,
  selectedCountryCode,
}) {
  const countriesRef = useRef([]);

  useEffect(() => {
    if (!globeRef.current) return;

    loadWorldGeoJSON()
      .then((geojson) => {
        countriesRef.current = geojson.features || [];
      })
      .catch((error) => {
        console.error("Failed to load world GeoJSON:", error);
      });
  }, [globeRef]);

  useEffect(() => {
    if (!globeRef.current || !countriesRef.current.length) return;

    globeRef.current
      .polygonsData(countriesRef.current)
      .polygonCapColor((country) =>
        getPolygonCapColor(country, events, selectedCountryCode, mode, weather)
      )
      .polygonSideColor(getPolygonSideColor)
      .polygonStrokeColor(() => "rgba(0, 0, 0, 0)")
      .polygonAltitude(0.008)
      .polygonLabel((country) => getPolygonLabel(country, mode, weather))
      .onPolygonClick((country) => {
        const code = country.properties?.ISO_A2 || country.properties?.ISO_A2_E;
        const name = country.properties?.NAME || country.properties?.ADMIN || "Unknown";

        if (code && code !== "-99") onSelectCountry({ code, name });
      });
  }, [globeRef, events, weather, mode, onSelectCountry, selectedCountryCode]);

  return countriesRef;
}
