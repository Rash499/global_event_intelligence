import { useRef } from "react";
import { useGlobeInit } from "./useGlobeInit";
import { useCountryPolygons } from "./useCountryPolygons";
import { useEventPoints } from "./useEventPoints";
import { useEventRings } from "./useEventRings";
import { useCameraFocus } from "./useCameraFocus";

export default function Globe({
  events,
  onSelectEvent,
  onSelectCountry,
  selectedCountryCode,
}) {
  const containerRef = useRef(null);
  const globeRef = useRef(null);

  useGlobeInit(containerRef, globeRef);
  useCountryPolygons({
    globeRef,
    events,
    onSelectCountry,
    selectedCountryCode,
  });
  useEventPoints({ globeRef, events, onSelectEvent });
  useEventRings({ globeRef, events });
  useCameraFocus({ globeRef, events, selectedCountryCode });

  return <div ref={containerRef} className="globe" />;
}
