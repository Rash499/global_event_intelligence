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
        "//unpkg.com/three-globe/example/img/earth-night.jpg"
      )
      .bumpImageUrl(
        "//unpkg.com/three-globe/example/img/earth-topology.png"
      )
      .backgroundColor("rgba(0,0,0,0)")
      .showAtmosphere(true)
      .atmosphereColor("#39c8ff")
      .atmosphereAltitude(0.18)
      .showGraticules(true)
      .pointsMerge(false)
      .enablePointerInteraction(true);

    globeRef.current = globe;

    const controls = globe.controls();
    controls.enableZoom = true;
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.32;
    controls.minDistance = 160;
    controls.maxDistance = 520;

    globe.pointOfView({ lat: 18, lng: 20, altitude: 2.15 }, 0);

    let resumeTimer;
    const pauseRotation = () => {
      controls.autoRotate = false;
      window.clearTimeout(resumeTimer);
      resumeTimer = window.setTimeout(() => {
        controls.autoRotate = true;
      }, 2200);
    };

    container.addEventListener("pointerdown", pauseRotation);
    container.addEventListener("wheel", pauseRotation, { passive: true });

    const resizeGlobe = () => {
      if (!container || !container.isConnected) {
        return;
      }

      const rect = container.getBoundingClientRect();

      if (rect.width <= 0 || rect.height <= 0) {
        return;
      }

      globe.width(rect.width).height(rect.height);
    };

    const resizeObserver = new ResizeObserver(resizeGlobe);
    resizeObserver.observe(container);
    resizeGlobe();

    return () => {
      resizeObserver.disconnect();
      window.clearTimeout(resumeTimer);
      container.removeEventListener("pointerdown", pauseRotation);
      container.removeEventListener("wheel", pauseRotation);

      globe.pointsData([]);
      globe.ringsData([]);
      globe.polygonsData([]);
      globe.controls()?.dispose();
      globe.renderer()?.dispose();

      if (globeRef.current === globe) {
        globeRef.current = null;
      }

      if (container.isConnected) {
        container.innerHTML = "";
      }
    };
  }, [containerRef, globeRef]);
}