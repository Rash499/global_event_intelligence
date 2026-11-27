import { useMemo } from "react";

/**
 * Presentation helpers shared across workspace views.
 *
 * Rules enforced here:
 *  - an unknown value renders as "not assessed"/"—", never as zero;
 *  - severity, intelligence confidence and operational priority are three
 *    different things and get three different treatments;
 *  - integer-only inputs are labelled as such (see ``formatCount``).
 */

export const NOT_ASSESSED = "not assessed";

export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatCount(value, singular, plural) {
  // An empty string is a missing value, not a zero count.
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${formatNumber(number)} ${number === 1 ? singular : plural || `${singular}s`}`;
}

export function formatPercent(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  // 0..1 ratio becomes a percentage; anything already > 1 is assumed percent.
  const ratio = Math.abs(number) <= 1 ? number * 100 : number;
  return `${ratio.toFixed(digits)}%`;
}

export const SEVERITY_BANDS = [
  { key: "critical", label: "Critical", min: 8.5, colour: "#ff5d7a" },
  { key: "high", label: "High", min: 6.5, colour: "#ff9f43" },
  { key: "moderate", label: "Moderate", min: 4.5, colour: "#ffd166" },
  { key: "low", label: "Low", min: 2.5, colour: "#36b8ff" },
  { key: "minimal", label: "Minimal", min: 0, colour: "#7d93a8" },
];

/** Severity band for a 0-10 severity value. Null stays null: never "minimal". */
export function severityBand(severity) {
  if (severity === null || severity === undefined || severity === "") return null;
  const number = Number(severity);
  if (!Number.isFinite(number)) return null;
  return SEVERITY_BANDS.find((band) => number >= band.min) || SEVERITY_BANDS.at(-1);
}

export function severityColour(severity) {
  return severityBand(severity)?.colour || "#4b5f73";
}

/** Confidence is a 0-1 evidence strength, not a severity. */
export function confidenceBand(confidence) {
  if (confidence === null || confidence === undefined) return null;
  const number = Number(confidence);
  if (!Number.isFinite(number)) return null;
  if (number >= 0.8) return { key: "high", label: "High confidence", colour: "#57e0ae" };
  if (number >= 0.6) return { key: "moderate", label: "Moderate confidence", colour: "#7bdcff" };
  if (number >= 0.4) return { key: "low", label: "Low confidence", colour: "#ffd166" };
  return { key: "very_low", label: "Very low confidence", colour: "#ff9f43" };
}

const PRIORITY_LABELS = {
  flash: { label: "Flash", colour: "#ff5d7a", rank: 5 },
  immediate: { label: "Immediate", colour: "#ff8f6b", rank: 4 },
  priority: { label: "Priority", colour: "#ffd166", rank: 3 },
  routine: { label: "Routine", colour: "#7bdcff", rank: 2 },
  background: { label: "Background", colour: "#7d93a8", rank: 1 },
};

export function priorityMeta(label) {
  const key = String(label || "").toLowerCase();
  return PRIORITY_LABELS[key] || { label: label || NOT_ASSESSED, colour: "#4b5f73", rank: 0 };
}

export const LOCATION_PRECISION = {
  exact: { label: "Exact coordinates", plottable: true, rank: 4 },
  city: { label: "City", plottable: true, rank: 3 },
  locality: { label: "Locality", plottable: true, rank: 3 },
  admin_region: { label: "Administrative region", plottable: true, rank: 2 },
  region: { label: "Region", plottable: true, rank: 2 },
  // Backend geolocation emits "approximate" (with real coordinates) for
  // "near/around <city>" reporting. It must plot - at reduced precision -
  // or a large share of located events silently vanish from the map.
  approximate: { label: "Approximate (near a named place)", plottable: true, rank: 2 },
  country: { label: "Country only", plottable: false, rank: 1 },
  unknown: { label: "Unknown location", plottable: false, rank: 0 },
};

export function locationPrecision(precision) {
  return LOCATION_PRECISION[String(precision || "unknown").toLowerCase()] || LOCATION_PRECISION.unknown;
}

export function isPlottable(event) {
  return Boolean(
    event &&
      event.latitude !== null &&
      event.latitude !== undefined &&
      event.longitude !== null &&
      event.longitude !== undefined &&
      locationPrecision(event.location_precision || (event.location && event.location.precision)).plottable
  );
}

const EVENT_STATES = {
  new: { label: "New", tone: "info" },
  developing: { label: "Developing", tone: "warn" },
  escalating: { label: "Escalating", tone: "danger" },
  stable: { label: "Stable", tone: "ok" },
  de_escalating: { label: "De-escalating", tone: "ok" },
  resolved: { label: "Resolved", tone: "muted" },
  archived: { label: "Archived", tone: "muted" },
  ongoing: { label: "Ongoing", tone: "warn" },
};

export function eventState(state) {
  return EVENT_STATES[String(state || "").toLowerCase()] || { label: state || "Unknown", tone: "muted" };
}

/** Turn a component breakdown object into sorted rows for display. */
export function breakdownRows(components, labels = {}) {
  if (!components || typeof components !== "object") return [];
  return Object.entries(components)
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .map(([key, value]) => ({
      key,
      label: labels[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      value,
    }))
    .sort((a, b) => b.value - a.value);
}

export function humanise(value) {
  if (!value) return "—";
  return String(value).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Group navigation items into their workspace groups, preserving order. */
export function useGroupedSections(sections) {
  return useMemo(() => {
    const groups = [];
    for (const section of sections) {
      const group = section.group || "Workspace";
      let bucket = groups.find((entry) => entry.name === group);
      if (!bucket) {
        bucket = { name: group, items: [] };
        groups.push(bucket);
      }
      bucket.items.push(section);
    }
    return groups;
  }, [sections]);
}
