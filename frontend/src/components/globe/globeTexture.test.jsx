import { describe, expect, it } from "vitest";

import globeInitSource from "./useGlobeInit.jsx?raw";

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
