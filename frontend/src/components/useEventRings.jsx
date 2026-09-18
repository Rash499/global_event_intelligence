import { useEffect } from "react";
import { getRingColor } from "./globeColors";

/**
 * Draws pulsing rings around events with importance >= 7.
 */
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
      .ringMaxRadius((event) => 2 + event.importance * 0.35)
      .ringPropagationSpeed(1.5)
      .ringRepeatPeriod(1400);
  }, [globeRef, events]);
}
