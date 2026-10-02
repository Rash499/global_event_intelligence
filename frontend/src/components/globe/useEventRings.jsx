import { useEffect } from "react";
import { getRingColor } from "./globeColors";

export function useEventRings({ globeRef, events }) {
  useEffect(() => {
    if (!globeRef.current) return;

    const importantEvents = events.filter(
      (event) =>
        event.latitude !== null &&
        event.longitude !== null &&
        event.importance >= 7
    );

    globeRef.current
      .ringsData(importantEvents)
      .ringLat("latitude")
      .ringLng("longitude")
      .ringColor(getRingColor)
      .ringMaxRadius((event) => 1.8 + event.importance * 0.28)
      .ringPropagationSpeed(1.15)
      .ringRepeatPeriod(1200);
  }, [globeRef, events]);
}