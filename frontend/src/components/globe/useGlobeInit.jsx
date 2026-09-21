import { useEffect } from "react";
import Globe from "globe.gl";

export function useGlobeInit(containerRef, globeRef) {
  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      console.warn("Globe container is not available.");
      return;
    }

    const globe = Globe()(container)
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

    const resizeGlobe = () => {
      // Do NOT use containerRef.current here.
      if (!container || !container.isConnected) {
        return;
      }

      const rect = container.getBoundingClientRect();

      if (rect.width <= 0 || rect.height <= 0) {
        return;
      }

      globe
        .width(rect.width)
        .height(rect.height);
    };

    const resizeObserver = new ResizeObserver(resizeGlobe);

    resizeObserver.observe(container);

    // Initial size
    resizeGlobe();

    return () => {
      resizeObserver.disconnect();

      if (globeRef.current === globe) {
        globeRef.current = null;
      }

      if (container.isConnected) {
        container.innerHTML = "";
      }
    };
  }, [containerRef, globeRef]);
}