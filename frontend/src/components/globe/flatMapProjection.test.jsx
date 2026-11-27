import { describe, expect, it } from "vitest";

import {
  FLAT_VIEW_H,
  FLAT_VIEW_W,
  countryCodeOf,
  featurePath,
  pointPlainLabel,
  projectEquirectangular,
} from "./flatMapProjection.jsx";

describe("flatMapProjection", () => {
  it("projects longitude/latitude linearly (equirectangular)", () => {
    expect(projectEquirectangular(0, 0)).toEqual([FLAT_VIEW_W / 2, FLAT_VIEW_H / 2]);
    expect(projectEquirectangular(-180, 90)).toEqual([0, 0]);
    expect(projectEquirectangular(180, -90)).toEqual([FLAT_VIEW_W, FLAT_VIEW_H]);
    // Tokyo is east/north of centre.
    const [x, y] = projectEquirectangular(139.65, 35.67);
    expect(x).toBeGreaterThan(FLAT_VIEW_W / 2);
    expect(y).toBeLessThan(FLAT_VIEW_H / 2);
  });

  it("builds closed SVG paths for polygon and multipolygon features", () => {
    const polygon = {
      geometry: {
        type: "Polygon",
        coordinates: [[[0, 0], [10, 0], [10, 10], [0, 0]]],
      },
    };
    const path = featurePath(polygon);
    expect(path.startsWith("M")).toBe(true);
    expect(path.endsWith("Z")).toBe(true);

    const multi = {
      geometry: {
        type: "MultiPolygon",
        coordinates: [[[[0, 0], [5, 0], [5, 5], [0, 0]]], [[[20, 20], [25, 20], [25, 25], [20, 20]]]],
      },
    };
    expect(featurePath(multi).match(/Z/g)).toHaveLength(2);
    expect(featurePath({ geometry: null })).toBe("");
    expect(featurePath({})).toBe("");
  });

  it("reads country codes, ignoring the -99 placeholder", () => {
    expect(countryCodeOf({ properties: { ISO_A2: "JP" } })).toBe("JP");
    expect(countryCodeOf({ properties: { ISO_A2: "-99", ISO_A2_E: "FR" } })).toBe(null);
    expect(countryCodeOf({ properties: {} })).toBe(null);
  });

  it("labels clusters and aggregates as derived positions, never as events", () => {
    expect(pointPlainLabel({ is_cluster: true, cluster_count: 4 })).toMatch(/average of reported locations/);
    expect(pointPlainLabel({ is_country_aggregate: true, title: "3 events in Japan" })).toMatch(/country-level aggregate/);
    expect(pointPlainLabel({ title: "Quake", country: "Japan" })).toBe("Quake — Japan");
  });
});
