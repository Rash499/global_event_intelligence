import { describe, expect, it } from "vitest";

import {
  confidenceBand,
  eventState,
  formatCount,
  formatNumber,
  formatPercent,
  isPlottable,
  locationPrecision,
  priorityMeta,
  severityBand,
  severityColour,
} from "./format.jsx";

describe("format helpers", () => {
  it("never renders an unknown number as zero", () => {
    for (const value of [null, undefined, "", "abc", NaN]) {
      expect(formatNumber(value)).toBe("—");
      expect(formatCount(value, "event")).toBe("—");
      expect(formatPercent(value)).toBe("—");
    }
    expect(formatNumber(0)).toBe("0");
    expect(formatCount(0, "event")).toBe("0 events");
  });

  it("pluralises counts from the actual number", () => {
    expect(formatCount(1, "event")).toBe("1 event");
    expect(formatCount(2, "event")).toBe("2 events");
    expect(formatCount(1, "copy", "copies")).toBe("1 copy");
    expect(formatCount(3, "copy", "copies")).toBe("3 copies");
  });

  it("treats ratios and percentages distinctly", () => {
    expect(formatPercent(0.42)).toBe("42%");
    expect(formatPercent(42)).toBe("42%");
    expect(formatPercent(0.425, 1)).toBe("42.5%");
  });
});

describe("severity banding", () => {
  it("bands the documented thresholds", () => {
    expect(severityBand(9.4).key).toBe("critical");
    expect(severityBand(8.5).key).toBe("critical");
    expect(severityBand(8.4).key).toBe("high");
    expect(severityBand(6.5).key).toBe("high");
    expect(severityBand(4.5).key).toBe("moderate");
    expect(severityBand(2.5).key).toBe("low");
    expect(severityBand(0).key).toBe("minimal");
  });

  it("returns null rather than 'minimal' for an unassessed event", () => {
    expect(severityBand(null)).toBeNull();
    expect(severityBand(undefined)).toBeNull();
    expect(severityBand("")).toBeNull();
    expect(severityColour(null)).toBe("#4b5f73");
  });
});

describe("confidence is separate from severity", () => {
  it("bands 0-1 evidence strength", () => {
    expect(confidenceBand(0.9).label).toBe("High confidence");
    expect(confidenceBand(0.65).label).toBe("Moderate confidence");
    expect(confidenceBand(0.45).label).toBe("Low confidence");
    expect(confidenceBand(0.2).label).toBe("Very low confidence");
    expect(confidenceBand(null)).toBeNull();
  });

  it("does not reuse severity colours for confidence", () => {
    expect(confidenceBand(0.9).colour).not.toBe(severityColour(9.4));
  });
});

describe("priority labels", () => {
  it("maps known labels and degrades to the API text", () => {
    expect(priorityMeta("flash").rank).toBe(5);
    expect(priorityMeta("ROUTINE").label).toBe("Routine");
    expect(priorityMeta("weird").label).toBe("weird");
    expect(priorityMeta(null).label).toBe("not assessed");
  });
});

describe("location honesty", () => {
  it("only calls a country-precision event plottable when it has coordinates and a point-capable precision", () => {
    expect(isPlottable({ latitude: 1, longitude: 2, location_precision: "city" })).toBe(true);
    expect(isPlottable({ latitude: 1, longitude: 2, location_precision: "exact" })).toBe(true);
    expect(isPlottable({ latitude: 1, longitude: 2, location_precision: "region" })).toBe(true);
    // A country-level event must never become a pin even if coordinates leak in.
    expect(isPlottable({ latitude: 1, longitude: 2, location_precision: "country" })).toBe(false);
    expect(isPlottable({ latitude: null, longitude: null, location_precision: "city" })).toBe(false);
    expect(isPlottable({ location_precision: "unknown" })).toBe(false);
    expect(isPlottable(null)).toBe(false);
  });

  it("reads nested location precision from the event envelope", () => {
    expect(isPlottable({ latitude: 5, longitude: 5, location: { precision: "country" } })).toBe(false);
    expect(locationPrecision("country").plottable).toBe(false);
    expect(locationPrecision(undefined).label).toBe("Unknown location");
  });
});

describe("event lifecycle labels", () => {
  it("maps states and keeps unknown text", () => {
    expect(eventState("escalating").tone).toBe("danger");
    expect(eventState("resolved").tone).toBe("muted");
    expect(eventState("made_up").label).toBe("made_up");
    expect(eventState(null).label).toBe("Unknown");
  });
});
