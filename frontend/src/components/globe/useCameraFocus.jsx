import { useEffect } from "react";

export function useCameraFocus({ globeRef, events, selectedCountryCode }) {
  useEffect(() => {
    if (!globeRef.current || !selectedCountryCode) return;

    const countryEvents = events.filter(
      (event) => event.country_code === selectedCountryCode
    );

    if (!countryEvents.length) return;

    const latitude =
      countryEvents.reduce((sum, event) => sum + event.latitude, 0) /
      countryEvents.length;
    const longitude =
      countryEvents.reduce((sum, event) => sum + event.longitude, 0) /
      countryEvents.length;

    globeRef.current.pointOfView(
      { lat: latitude, lng: longitude, altitude: 1.6 },
      1200
    );
  }, [globeRef, selectedCountryCode, events]);
}
