import { describe, expect, it } from "vitest";

import globeInitSource from "./useGlobeInit.jsx?raw";
import countryPolygonsSource from "./useCountryPolygons.jsx?raw";

/**
 * Guards the attractive-globe setup: the night-earth texture must stay
 * bundled with the app (same-origin) and must never go back to a remote
 * CDN texture, which caused the three.js "Texture is immutable" error.
 */
describe("globe texture", () => {
  it("uses the bundled night-earth texture, loaded once via TextureLoader", () => {
    expect(globeInitSource).toContain("/textures/earth-night.jpg");
    expect(globeInitSource).toContain("TextureLoader");
    expect(globeInitSource).toContain("earthTexture.dispose()");
  });

  it("never references remote texture CDNs", () => {
    expect(globeInitSource).not.toContain("unpkg.com");
    expect(globeInitSource).not.toMatch(/globeImageUrl|bumpImageUrl/);
  });
});

describe("country polygon borders", () => {
  it("sets polygon geometry once with transitions disabled (no border glitch)", () => {
    expect(countryPolygonsSource).toContain("polygonsTransitionDuration(0)");
    // Geometry is set in exactly one effect; colours are accessor-only updates.
    expect(countryPolygonsSource.match(/polygonsData\(countries\)/g)).toHaveLength(1);
    expect(countryPolygonsSource).toContain("polygonAltitude(0.008)");
    // Stroke lines are coplanar line geometry and z-fight on rotation;
    // borders must come from caps/sides, never a stroke colour.
    expect(countryPolygonsSource).toContain('polygonStrokeColor(() => "rgba(0, 0, 0, 0)")');
  });
});
