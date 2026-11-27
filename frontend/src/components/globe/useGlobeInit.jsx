import { useEffect } from "react";
import Globe from "globe.gl";
import * as THREE from "three";

export function useGlobeInit(containerRef, globeRef) {
  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      console.warn("Globe container is not available.");
      return;
    }

    // No remote earth textures: the previous unpkg globe/bump images made
    // three.js re-upload immutable textures (WebGL "glTexStorage2D: Texture
    // is immutable") and added an unvetted CDN dependency at runtime. The
    // sphere is a plain material; country polygons drawn from the bundled
    // world.geojson provide the landmasses.
    const globe = Globe()(container)
      .globeMaterial(
        new THREE.MeshPhongMaterial({ color: "#0a2a44", shininess: 8 })
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