const CANDIDATES = ["/world.geojson", "world.geojson"];
let cachedData = null;
let inflight = null;

async function fetchFirst(urls) {
  let lastError = null;
  for (const url of urls) {
    try {
      const response = await fetch(url, { cache: "force-cache" });
      if (!response.ok) {
        lastError = new Error(`Failed to load ${url}: ${response.status}`);
        continue;
      }
      const text = await response.text();
      const trimmed = text.trimStart();
      if (trimmed.startsWith("<!doctype") || trimmed.startsWith("<html")) {
        lastError = new Error(`Server returned HTML for ${url}.`);
        continue;
      }
      const data = JSON.parse(text);
      if (data?.type === "Topology") {
        throw new Error("TopoJSON is not supported; expected GeoJSON.");
      }
      if (data?.type !== "FeatureCollection" || !Array.isArray(data.features)) {
        lastError = new Error(`${url} is not a GeoJSON FeatureCollection.`);
        continue;
      }
      console.log("Loaded world.geojson:", { url, features: data.features.length });
      return data;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Could not load world.geojson.");
}

export async function loadWorldGeoJSON() {
  if (cachedData) return cachedData;
  if (inflight) return inflight;
  inflight = fetchFirst(CANDIDATES)
    .then((data) => {
      cachedData = data;
      inflight = null;
      return data;
    })
    .catch((error) => {
      inflight = null;
      throw error;
    });
  return inflight;
}

export function clearWorldGeoJSONCache() {
  cachedData = null;
  inflight = null;
}

const CODE_ALIASES = { UK: "GB", EL: "GR", XK: "XK" };

export function normalizeCountryCode(code) {
  const upper = String(code || "").toUpperCase().trim();
  return CODE_ALIASES[upper] || upper;
}

function featureCodes(props = {}) {
  const keys = [
    "ISO_A2", "ISO_A2_E", "ISO_A2_EH", "WB_A2",
    "ISO_A3", "ISO_A3_EH", "ADM0_A3", "ADM0_A3_UN", "ADM0_A3_WB",
    "GU_A3", "SU_A3", "BRK_A3", "SOV_A3", "ISO_N3", "POSTAL",
  ];
  const out = new Set();
  keys.forEach((key) => {
    const value = props[key];
    if (typeof value === "string" && value.trim() && value.trim() !== "-99") {
      out.add(value.trim().toUpperCase());
    } else if (Number.isFinite(value)) {
      out.add(String(value));
    }
  });
  return out;
}

function featureNames(props = {}) {
  const keys = [
    "NAME", "ADMIN", "NAME_LONG", "FORMAL_EN", "BRK_NAME",
    "NAME_SORT", "GEOUNIT", "SOVEREIGNT", "NAME_EN",
  ];
  const out = new Set();
  keys.forEach((key) => {
    const value = props[key];
    if (typeof value === "string" && value.trim()) out.add(value.trim().toLowerCase());
  });
  return out;
}

const NAME_ALIASES = {
  "united states of america": ["united states", "usa", "us"],
  "united kingdom": ["uk", "great britain", "britain", "england"],
  russia: ["russian federation"],
  "south korea": ["korea, south", "republic of korea", "korea"],
  "north korea": ["korea, north", "dem. rep. korea"],
  iran: ["iran (islamic republic of)", "islamic republic of iran"],
  tanzania: ["united republic of tanzania"],
  syria: ["syrian arab republic"],
  venezuela: ["venezuela (bolivarian republic of)"],
  vietnam: ["viet nam"],
  laos: ["lao people's democratic republic"],
  moldova: ["republic of moldova"],
  bolivia: ["bolivia (plurinational state of)"],
  "cape verde": ["cabo verde"],
  swaziland: ["eswatini"],
  "czech republic": ["czechia", "czech rep."],
};

function expandNameVariants(name) {
  const lower = String(name || "").toLowerCase().trim();
  if (!lower) return [];
  const variants = new Set([lower]);
  Object.entries(NAME_ALIASES).forEach(([key, aliases]) => {
    if (lower === key || aliases.includes(lower)) {
      variants.add(key);
      aliases.forEach((alias) => variants.add(alias));
    }
  });
  return [...variants];
}

export function matchCountryFeatures(features = [], countryCode, countryName) {
  const code = normalizeCountryCode(countryCode);
  const variants = expandNameVariants(countryName);
  const scored = [];
  (features || []).forEach((feature) => {
    const props = feature?.properties || {};
    const codes = featureCodes(props);
    const names = featureNames(props);
    let score = 0;
    let reason = "";
    if (code && codes.has(code)) {
      score = 100;
      reason = "iso-code";
    } else if (code && code.length === 2) {
      const threeLetterHit = [...codes].some((candidate) => candidate.startsWith(code));
      if (threeLetterHit) {
        score = 40;
        reason = "code-prefix";
      }
    }
    if (!score && variants.length) {
      for (const variant of variants) {
        if (names.has(variant)) {
          score = 90;
          reason = "exact-name";
          break;
        }
      }
      if (!score) {
        for (const variant of variants) {
          const hit = [...names].some(
            (candidate) => candidate.includes(variant) || variant.includes(candidate)
          );
          if (hit) {
            score = 60;
            reason = "fuzzy-name";
            break;
          }
        }
      }
    }
    if (score > 0) scored.push({ feature: feature, score: score, reason: reason });
  });
  scored.sort((a, b) => b.score - a.score);
  return scored;
}
