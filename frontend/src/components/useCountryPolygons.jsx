import { useEffect, useRef } from "react";
import {
  getPolygonCapColor,
  getPolygonSideColor,
  getPolygonStrokeColor,
  getPolygonLabel,
} from "./globeColors";

/**
 * Loads /public/world.geojson and renders it as clickable country
 * polygons, colored by the events in each country.
 */
export function useCountryPolygons({
  globeRef,
  events,
  onSelectCountry,
  selectedCountryCode,
}) {
  const countriesRef = useRef([]);

  useEffect(() => {
    if (!globeRef.current) return;

    fetch("/world.geojson")
      .then((response) => response.json())
      .then((geojson) => {
        const countries = geojson.features || [];
        countriesRef.current = countries;

        globeRef.current
          .polygonsData(countries)
          .polygonCapColor((country) =>
            getPolygonCapColor(country, events, selectedCountryCode)
          )
          .polygonSideColor(getPolygonSideColor)
          .polygonStrokeColor(getPolygonStrokeColor)
          .polygonAltitude(0.008)
          .polygonLabel(getPolygonLabel)
          .onPolygonClick((country) => {
            const code =
              country.properties?.ISO_A2 || country.properties?.ISO_A2_E;
            const name =
              country.properties?.NAME ||
              country.properties?.ADMIN ||
              "Unknown";

            if (code && code !== "-99") {
              onSelectCountry({ code, name });
            }
          });
      })
      .catch((error) => {
        console.error("Failed to load world GeoJSON:", error);
      });
  }, [globeRef, events, onSelectCountry, selectedCountryCode]);

  return countriesRef;
}
