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

    // Attractive night-earth look, without the old WebGL texture error:
    // the earth texture is bundled with the app (public/textures/, copied
    // from the three-globe example assets) instead of hot-loaded from
    // unpkg, and it is loaded exactly once through our own TextureLoader
    // with fixed settings (sRGB, no re-uploads) and disposed on unmount.
    // The previous setup let globe.gl juggle remote globe+bump textures,
    // which produced "glTexStorage2D: Texture is immutable" in three.js.
    const earthTexture = new THREE.TextureLoader().load(
      "/textures/earth-night.jpg"
    );
    earthTexture.colorSpace = THREE.SRGBColorSpace;
    earthTexture.anisotropy = 4;

    const globe = Globe()(container)
      .globeMaterial(
        new THREE.MeshPhongMaterial({
          map: earthTexture,
          shininess: 12,
          specular: new THREE.Color("#1a3a52"),
        })
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
      // Dispose our texture/material so a remount (React StrictMode) never
      // reuses a texture already uploaded to a disposed WebGL context.
      earthTexture.dispose();
      globe.globeMaterial()?.dispose?.();

      if (globeRef.current === globe) {
        globeRef.current = null;
      }

      if (container.isConnected) {
        container.innerHTML = "";
      }
    };
  }, [containerRef, globeRef]);
}