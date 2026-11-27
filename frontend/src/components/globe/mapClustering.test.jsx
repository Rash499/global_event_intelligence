import { describe, expect, it } from "vitest";

import { clusterMapPoints } from "./mapClustering.jsx";

const pin = (id, latitude, longitude, extra = {}) => ({
  id,
  title: `Event ${id}`,
  latitude,
  longitude,
  importance: 5,
  ...extra,
});

describe("clusterMapPoints", () => {
  it("merges nearby pins into a disclosed cluster at the average position", () => {
    const points = clusterMapPoints([pin(1, 35.0, 139.0), pin(2, 36.0, 139.5), pin(3, -33.0, 151.0)]);
    const cluster = points.find((point) => point.is_cluster);
    expect(cluster).toBeTruthy();
    expect(cluster.cluster_count).toBe(2);
    expect(cluster.member_ids).toEqual([1, 2]);
    // Centroid is the average of reported locations, never a stored position.
    expect(cluster.latitude).toBeCloseTo(35.5);
    expect(cluster.longitude).toBeCloseTo(139.25);
    expect(cluster.events.map((event) => event.id)).toEqual([1, 2]);
    // The distant pin passes through untouched.
    expect(points.find((point) => point.id === 3)).toBeTruthy();
    expect(points).toHaveLength(2);
  });

  it("uses the highest member importance for cluster styling", () => {
    const points = clusterMapPoints([
      pin(1, 35.0, 139.0, { importance: 4 }),
      pin(2, 35.4, 139.4, { importance: 9 }),
    ]);
    expect(points[0].importance).toBe(9);
  });

  it("passes single pins and empty input through unchanged", () => {
    expect(clusterMapPoints([])).toEqual([]);
    const single = [pin(1, 10, 20)];
    expect(clusterMapPoints(single)).toEqual(single);
  });

  it("never clusters country aggregates (already country rollups)", () => {
    const aggregate = pin(99, 35.5, 139.5, { is_country_aggregate: true });
    const points = clusterMapPoints([pin(1, 35.0, 139.0), pin(2, 36.0, 139.5), aggregate]);
    // The aggregate is excluded from pin clustering; the caller renders it
    // separately so it can never be swallowed into a pin cluster.
    expect(points.some((point) => point.id === 99)).toBe(false);
    expect(points.find((point) => point.is_cluster).cluster_count).toBe(2);
  });
});
