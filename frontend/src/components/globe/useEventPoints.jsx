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
      .pointAltitude(0.025)
      .pointRadius(0.35)
      .pointResolution(16)
      .pointColor(getPointColor)
      .pointLabel(getPointLabel)
      .onPointClick((event) => onSelectEvent(event));
  }, [globeRef, events, enabled, onSelectEvent]);
}
