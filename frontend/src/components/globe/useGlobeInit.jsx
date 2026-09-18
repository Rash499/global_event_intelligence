import { useEffect } from "react";
import GlobeGL from "globe.gl";

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

    const resizeGlobe = () => {
      const { width, height } = containerRef.current.getBoundingClientRect();

      if (width > 0 && height > 0) {
        globe.width(width).height(height);
        globe.pointOfView({ lat: 0, lng: 0, altitude: 2.5 }, 0);
      }
    };

    const resizeObserver = new ResizeObserver(resizeGlobe);
    resizeObserver.observe(containerRef.current);
    resizeGlobe();
    globeRef.current = globe;

    return () => {
      resizeObserver.disconnect();
      if (containerRef.current) containerRef.current.innerHTML = "";
      globeRef.current = null;
    };
  }, [containerRef, globeRef]);
}
