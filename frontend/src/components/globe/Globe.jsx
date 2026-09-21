import { useRef } from "react";
import { useGlobeInit } from "./useGlobeInit";
import { useCountryPolygons } from "./useCountryPolygons";
import { useEventPoints } from "./useEventPoints";
import { useEventRings } from "./useEventRings";
import { useCameraFocus } from "./useCameraFocus";
import { useWeatherPoints } from "./useWeatherPoints";

export default function Globe({
  mode = "events",
  events,
  weather,
  onSelectEvent,
  onSelectWeather,
  onSelectCountry,
  selectedCountryCode,
}) {
  const containerRef = useRef(null);
  const globeRef = useRef(null);

  useGlobeInit(containerRef, globeRef);

  useCountryPolygons({
    globeRef,
    events,
    weather,
    mode,
    onSelectCountry,
    selectedCountryCode,
  });

  useEventPoints({
    globeRef,
    events: mode === "events" ? events : [],
    onSelectEvent,
  });

  useEventRings({
    globeRef,
    events: mode === "events" ? events : [],
  });

  useWeatherPoints({
    globeRef,
    weather: mode === "weather" ? weather : [],
    onSelectWeather,
  });

  useCameraFocus({
    globeRef,
    events: mode === "events" ? events : [],
    selectedCountryCode,
  });

  return <div ref={containerRef} className="globe" />;
}
