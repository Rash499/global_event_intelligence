import { describe, expect, it } from "vitest";

import {
  ALL_LAYER_IDS,
  MAP_LAYERS,
  categoriesForLayers,
  layerForCategory,
  layerFreshness,
} from "./mapLayers.jsx";

// The taxonomy's 16 stable category keys (backend taxonomy.py v1.0). The
// layer registry must cover every one exactly once, or events in an
// uncovered category could never be shown or hidden on the map.
const TAXONOMY_CATEGORIES = [
  "armed_conflict", "political_development", "protest_unrest",
  "terrorism_extremism", "natural_disaster", "severe_weather",
  "public_health", "humanitarian", "economic_financial",
  "energy_infrastructure", "transportation", "cyber_technology",
  "crime_public_safety", "international_relations", "environmental", "other",
];

describe("mapLayers registry", () => {
  it("covers every taxonomy category exactly once", () => {
    const covered = MAP_LAYERS.flatMap((layer) => layer.categories);
    expect([...covered].sort()).toEqual([...TAXONOMY_CATEGORIES].sort());
    expect(new Set(covered).size).toBe(covered.length);
    expect(ALL_LAYER_IDS).toHaveLength(MAP_LAYERS.length);
  });

  it("maps categories to layers, defaulting uncategorised events to other", () => {
    expect(layerForCategory("armed_conflict")).toBe("conflict_security");
    expect(layerForCategory("severe_weather")).toBe("natural_weather");
    expect(layerForCategory(null)).toBe("other");
    expect(layerForCategory("nonsense")).toBe("other");
  });

  it("expands enabled layers to their categories", () => {
    expect(categoriesForLayers(["natural_weather"])).toEqual([
      "natural_disaster", "severe_weather", "environmental",
    ]);
    expect(categoriesForLayers([])).toEqual([]);
    expect(categoriesForLayers(ALL_LAYER_IDS)).toHaveLength(16);
  });

  it("rolls per-category freshness up to layers", () => {
    const stats = layerFreshness([
      { category: "natural_disaster", events: 3, latest_event_at: "2026-11-27T10:00:00Z" },
      { category: "severe_weather", events: 2, latest_event_at: "2026-11-27T12:00:00Z" },
      { category: "armed_conflict", events: 1, latest_event_at: "2026-11-26T09:00:00Z" },
    ]);
    expect(stats.natural_weather).toEqual({
      events: 5,
      latest_event_at: "2026-11-27T12:00:00Z",
    });
    expect(stats.conflict_security.events).toBe(1);
    // A layer with no stored events reports zero honestly, not a guess.
    expect(stats.health_humanitarian).toEqual({ events: 0, latest_event_at: null });
    expect(layerFreshness([]).other.events).toBe(0);
  });
});
