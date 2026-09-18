import { useEffect } from "react";
import GlobeGL from "globe.gl";

/**
 * Creates the globe.gl instance inside containerRef and stores it in
 * globeRef. Tears it down on unmount.
 */
export function useGlobeInit(containerRef, globeRef) {
  useEffect(() => {
    if (!containerRef.current) return;

    const globe = GlobeGL()(containerRef.current)
      .globeImageUrl("//unpkg.com/three-globe/example/img/earth-blue-marble.jpg")
      .bumpImageUrl("//unpkg.com/three-globe/example/img/earth-topology.png")
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
  }, [containerRef, globeRef]);
}
