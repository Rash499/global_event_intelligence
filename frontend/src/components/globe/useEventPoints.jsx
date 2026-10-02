import { useEffect } from "react";
import { getPointColor, getPointLabel } from "./globeColors";

export function useEventPoints({ globeRef, events, enabled, onSelectEvent }) {
  useEffect(() => {
    if (!globeRef.current || !enabled) return;

    const validEvents = events.filter(
      (event) => event.latitude !== null && event.longitude !== null
    );

    globeRef.current
      .pointsData(validEvents)
      .pointLat("latitude")
      .pointLng("longitude")
      .pointAltitude((event) => 0.035 + Math.min(0.045, event.importance * 0.006))
      .pointRadius((event) => 0.24 + Math.min(0.22, event.importance * 0.025))
      .pointResolution(20)
      .pointColor(getPointColor)
      .pointLabel(getPointLabel)
      .onPointClick((event) => onSelectEvent(event));
  }, [globeRef, events, enabled, onSelectEvent]);
}