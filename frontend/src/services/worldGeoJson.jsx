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

// ISO 2-letter codes only. Natural Earth's POSTAL field is a mail code that
// collides across countries (eSwatini=ES, N. Cyprus=CN, Somaliland=SL).
const CODE_KEYS = [
  "ISO_A2", "ISO_A2_E", "ISO_A2_EH", "WB_A2",
  "ISO_A3", "ISO_A3_EH", "ADM0_A3", "ADM0_A3_UN", "ADM0_A3_WB",
  "GU_A3", "SU_A3", "BRK_A3", "SOV_A3", "ISO_N3",
];

function featureCodes(props = {}, keys = CODE_KEYS) {
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

/**
 * Agency codes describing the unit itself. Sovereign codes (SOV_A3) are left
 * out on purpose: Natural Earth reuses them for dependencies, so "FR1" would
 * pull New Caledonia into the French outline.
 */
const PREFIX_CODE_KEYS = [
  "ISO_A3", "ISO_A3_EH", "ADM0_A3", "ADM0_A3_UN", "ADM0_A3_WB",
  "GU_A3", "SU_A3", "BRK_A3",
];

// Short aliases like "us"/"uk" must never match inside another word.
const MIN_TOKEN_LENGTH = 4;

function significantTokens(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(" ")
    .filter((token) => token.length >= MIN_TOKEN_LENGTH);
}

/** True when every significant word of the variant appears in a candidate name. */
function tokenSubsetOf(variant, candidateNames) {
  const needed = significantTokens(variant);
  if (!needed.length) return false;

  return candidateNames.some((name) => {
    const tokens = new Set(significantTokens(name));
    return needed.every((token) => tokens.has(token));
  });
}

// Self-identifying names only: SOVEREIGNT belongs to the parent country, so
// including it would attach dependencies (e.g. New Caledonia) to France.
function featureNames(props = {}) {
  const keys = [
    "NAME", "ADMIN", "NAME_LONG", "FORMAL_EN", "BRK_NAME",
    "NAME_SORT", "GEOUNIT", "NAME_EN",
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

  // Tiers are exclusive: a confident ISO hit must not be diluted with
  // dependencies or look-alike names (e.g. Falkland Is. widening the UK outline,
  // or Puerto Rico widening the US outline).
  const tiers = [[], [], [], []];
  (features || []).forEach((feature) => {
    const props = feature?.properties || {};
    const codes = featureCodes(props);

    if (code && codes.has(code)) {
      tiers[0].push({ feature: feature, score: 100, reason: "iso-code" });
      return;
    }

    const names = featureNames(props);
    if (variants.some((variant) => names.has(variant))) {
      tiers[1].push({ feature: feature, score: 90, reason: "exact-name" });
      return;
    }

    if (variants.some((variant) => tokenSubsetOf(variant, [...names]))) {
      tiers[2].push({ feature: feature, score: 60, reason: "name-words" });
      return;
    }

    if (code && code.length === 2) {
      const prefixHit = [...featureCodes(props, PREFIX_CODE_KEYS)].some(
        (candidate) => /^[A-Z]+$/.test(candidate) && candidate.startsWith(code)
      );
      if (prefixHit) tiers[3].push({ feature: feature, score: 40, reason: "code-prefix" });
    }
  });

  const matched = tiers.find((tier) => tier.length);
  if (!matched) return [];
  matched.sort((a, b) => b.score - a.score);
  return matched;
}
