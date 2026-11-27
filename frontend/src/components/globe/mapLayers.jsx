/**
 * Map layer registry — the single source of truth for the event map's
 * toggleable layers (the worldmonitor layer-catalogue pattern, reimplemented
 * for our taxonomy).
 *
 * Each layer groups taxonomy categories that belong together on a map. The
 * MapView layer panel, the backend `categories` filter and the per-layer
 * freshness display are all driven from this list, so a layer can never be
 * offered in the UI that the map cannot actually filter by.
 *
 * No layer introduces a new data source: every layer renders events already
 * collected by the existing (free) provider pipeline.
 */
export const MAP_LAYERS = [
  {
    id: "conflict_security",
    label: "Conflict & security",
    glyph: "⚔",
    description: "Armed conflict, terrorism and extremism reporting.",
    categories: ["armed_conflict", "terrorism_extremism"],
  },
  {
    id: "politics_unrest",
    label: "Politics & unrest",
    glyph: "⚑",
    description: "Political developments, protests, civil unrest and diplomacy.",
    categories: ["political_development", "protest_unrest", "international_relations"],
  },
  {
    id: "natural_weather",
    label: "Natural & weather",
    glyph: "⛈",
    description: "Natural disasters, severe weather and environmental incidents.",
    categories: ["natural_disaster", "severe_weather", "environmental"],
  },
  {
    id: "health_humanitarian",
    label: "Health & humanitarian",
    glyph: "✚",
    description: "Public-health events and humanitarian crises.",
    categories: ["public_health", "humanitarian"],
  },
  {
    id: "economy_infrastructure",
    label: "Economy & infrastructure",
    glyph: "⚡",
    description: "Economic/financial developments, energy, infrastructure and transport.",
    categories: ["economic_financial", "energy_infrastructure", "transportation"],
  },
  {
    id: "cyber_safety",
    label: "Cyber & public safety",
    glyph: "🛡",
    description: "Cyber/technology incidents and crime or public-safety events.",
    categories: ["cyber_technology", "crime_public_safety"],
  },
  {
    id: "other",
    label: "Other / unclassified",
    glyph: "•",
    description: "Events the classifier could not place in a category.",
    categories: ["other"],
  },
];

export const ALL_LAYER_IDS = MAP_LAYERS.map((layer) => layer.id);

const LAYER_BY_CATEGORY = new Map();
for (const layer of MAP_LAYERS) {
  for (const category of layer.categories) LAYER_BY_CATEGORY.set(category, layer.id);
}

/** Layer id for a taxonomy category; uncategorised events fall into "other". */
export function layerForCategory(category) {
  return LAYER_BY_CATEGORY.get(category) || "other";
}

/** Taxonomy categories covered by the given enabled layer ids. */
export function categoriesForLayers(layerIds) {
  const enabled = new Set(layerIds);
  return MAP_LAYERS.filter((layer) => enabled.has(layer.id)).flatMap(
    (layer) => layer.categories
  );
}

/**
 * Roll the backend's per-category freshness rows up to per-layer figures, so
 * the layer panel can show "12 events · latest 2h ago" per layer. Categories
 * absent from the payload count as zero — honestly, because freshness is
 * computed over stored events only.
 */
export function layerFreshness(categoryFreshness = []) {
  const byCategory = new Map(
    (categoryFreshness || []).map((row) => [row.category, row])
  );
  const result = {};
  for (const layer of MAP_LAYERS) {
    let events = 0;
    let latest = null;
    for (const category of layer.categories) {
      const row = byCategory.get(category);
      if (!row) continue;
      events += row.events || 0;
      if (row.latest_event_at && (!latest || row.latest_event_at > latest)) {
        latest = row.latest_event_at;
      }
    }
    result[layer.id] = { events, latest_event_at: latest };
  }
  return result;
}
