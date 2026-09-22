import { useEffect, useState } from "react";
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
  const [countries, setCountries] = useState([]);

  useEffect(() => {
    let cancelled = false;

    loadWorldGeoJSON()
      .then((geojson) => {
        if (!cancelled) setCountries(geojson.features || []);
      })
      .catch((error) => {
        if (!cancelled) console.error("Failed to load world GeoJSON:", error);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const globe = globeRef.current;
    if (!globe || !countries.length) return;

    globe
      .polygonsData(countries)
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
  }, [countries, events, weather, mode, onSelectCountry, selectedCountryCode, globeRef]);
}
