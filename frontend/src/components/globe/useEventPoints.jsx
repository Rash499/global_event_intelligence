import { useEffect } from "react";
import { getPointColor, getPointLabel } from "./globeColors";

export function useEventPoints({ globeRef, events, onSelectEvent }) {
  useEffect(() => {
    if (!globeRef.current) return;

    const validEvents = events.filter(
      (event) => event.latitude !== null && event.longitude !== null
    );

    globeRef.current
      .pointsData(validEvents)
      .pointLat("latitude")
      .pointLng("longitude")
      .pointAltitude((event) => 0.02 + event.importance * 0.012)
      .pointRadius((event) => 0.5 + event.importance * 0.09)
      .pointColor(getPointColor)
      .pointLabel(getPointLabel)
      .onPointClick((event) => onSelectEvent(event));
  }, [globeRef, events, onSelectEvent]);
}
