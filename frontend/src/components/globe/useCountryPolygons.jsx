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

  // Set the polygon *geometry* exactly once per GeoJSON load.
  //
  // Previously a single effect re-ran on every events/weather change (new
  // array identities on each refresh) and called polygonsData() again.
  // globe.gl animates polygon altitude for 1000ms by default on every data
  // set, so the country borders were in a near-constant transition —
  // visibly glitching/flickering — and the low 0.008 altitude also
  // z-fought with the textured sphere at grazing angles.
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe || !countries.length) return;

    globe
      .polygonsData(countries)
      // No altitude animation when data (re)sets: borders must be static.
      .polygonsTransitionDuration(0)
      .polygonSideColor(getPolygonSideColor)
      .polygonStrokeColor(() => "rgba(130, 205, 255, 0.38)")
      // Slightly higher cap separates borders from the sphere texture and
      // stops depth-fighting shimmer while rotating.
      .polygonAltitude(0.015);
  }, [countries, globeRef]);

  // Colours, labels and clicks are accessors: updating them re-styles the
  // existing polygons without touching geometry, so event/weather refreshes
  // no longer restart any polygon transition.
  useEffect(() => {
    const globe = globeRef.current;
    if (!globe || !countries.length) return;

    globe
      .polygonCapColor((country) =>
        getPolygonCapColor(country, events, selectedCountryCode, mode, weather)
      )
      .polygonLabel((country) => getPolygonLabel(country, mode, weather))
      .onPolygonClick((country) => {
        const code = country.properties?.ISO_A2 || country.properties?.ISO_A2_E;
        const name = country.properties?.NAME || country.properties?.ADMIN || "Unknown";

        if (code && code !== "-99") onSelectCountry({ code, name });
      });
  }, [countries, events, weather, mode, onSelectCountry, selectedCountryCode, globeRef]);
}
