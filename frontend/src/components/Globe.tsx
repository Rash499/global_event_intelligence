import { useEffect, useRef } from "react";
import GlobeGL from "globe.gl";
import { EventItem } from "../types";

interface GlobeProps {
  events: EventItem[];
  onSelect: (event: EventItem) => void;
}

export default function Globe({
  events,
  onSelect,
}: GlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const globeRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const globe = GlobeGL()(containerRef.current)
      .globeImageUrl(
        "//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
      )
      .bumpImageUrl(
        "//unpkg.com/three-globe/example/img/earth-topology.png"
      )
      .backgroundColor("rgba(0,0,0,0)")
      .showAtmosphere(true)
      .atmosphereColor("#4aa8df")
      .atmosphereAltitude(0.15)
      .pointsMerge(false);

    globeRef.current = globe;

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }

      globeRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!globeRef.current) return;

    const validEvents = events.filter(
      (event) =>
        event.latitude !== null &&
        event.longitude !== null
    );

    globeRef.current
      .pointsData(validEvents)
      .pointLat("latitude")
      .pointLng("longitude")
      .pointAltitude(
        (event: EventItem) =>
          0.02 + event.importance * 0.012
      )
      .pointRadius(
        (event: EventItem) =>
          0.7 + event.importance * 0.1
      )
      .pointColor(() => "#ff4d6d")
      .pointLabel(
        (event: EventItem) => `
          <div style="
            background:#07111f;
            padding:10px 14px;
            border-radius:8px;
            color:white;
            font-family:Arial;
          ">
            <strong>${event.title}</strong>
            <br/>
            <small>
              ${event.country ?? "Global"} ·
              Importance ${event.importance}/10
            </small>
          </div>
        `
      )
      .onPointClick((event: EventItem) => {
        onSelect(event);
      });
  }, [events, onSelect]);

  return (
    <div
      ref={containerRef}
      className="globe"
    />
  );
}