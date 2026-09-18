import { useEffect } from "react";

/**
 * When selectedCountryCode changes, pans the camera to the average
 * lat/lng of that country's events.
 */
export function useCameraFocus({ globeRef, events, selectedCountryCode }) {
  useEffect(() => {
    if (!globeRef.current || !selectedCountryCode) return;

    const countryEvents = events.filter(
      (event) => event.country_code === selectedCountryCode
    );

    if (!countryEvents.length) return;

    const latitudes = countryEvents.map((event) => event.latitude);
    const longitudes = countryEvents.map((event) => event.longitude);

    const latitude =
      latitudes.reduce((sum, value) => sum + value, 0) / latitudes.length;
    const longitude =
      longitudes.reduce((sum, value) => sum + value, 0) / longitudes.length;

    globeRef.current.pointOfView({ lat: latitude, lng: longitude, altitude: 1.6 }, 1200);
  }, [globeRef, selectedCountryCode, events]);
}
