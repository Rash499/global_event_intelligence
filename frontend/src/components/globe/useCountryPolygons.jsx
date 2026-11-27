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
      // No altitude animation when data (re)sets: borders must be static.
      // Set this *before* polygonsData so even the first load never animates.
      .polygonsTransitionDuration(0)
      .polygonsData(countries)
      .polygonSideColor(getPolygonSideColor)
      // No stroke lines: three-globe draws strokes as 1px line geometry at
      // exactly cap altitude, coplanar with the cap surface. On a rotating
      // globe they z-fight and alias - the visible "glitching borders".
      // Country separation comes from the translucent caps + side walls
      // over the night texture (the original, stable configuration).
      .polygonStrokeColor(() => "rgba(0, 0, 0, 0)")
      .polygonAltitude(0.008);
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
