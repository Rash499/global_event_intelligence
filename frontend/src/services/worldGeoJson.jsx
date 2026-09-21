const WORLD_GEOJSON_URL = "/world.geojson";
let worldGeoJSONPromise;

export async function loadWorldGeoJSON() {
  if (worldGeoJSONPromise) return worldGeoJSONPromise;

  worldGeoJSONPromise = fetch(WORLD_GEOJSON_URL, {
    cache: "no-cache",
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(
          `Failed to load world.geojson: ${response.status} ${response.statusText}`
        );
      }

      const contentType = response.headers.get("content-type") || "";
      const text = await response.text();

      if (
        text.trimStart().startsWith("<!doctype") ||
        text.trimStart().startsWith("<html")
      ) {
        throw new Error(
          `The server returned HTML instead of world.geojson. Requested: ${response.url}`
        );
      }

      let data;

      try {
        data = JSON.parse(text);
      } catch {
        throw new Error("world.geojson was returned but it is not valid JSON.");
      }

      if (data.type !== "FeatureCollection") {
        throw new Error("world.geojson must be a GeoJSON FeatureCollection.");
      }

      if (!Array.isArray(data.features)) {
        throw new Error("world.geojson does not contain a valid features array.");
      }

      console.log("Loaded world.geojson successfully:", {
        url: response.url,
        status: response.status,
        contentType,
        features: data.features.length,
      });

      return data;
    })
    .catch((error) => {
      worldGeoJSONPromise = undefined;
      throw error;
    });

  return worldGeoJSONPromise;
}