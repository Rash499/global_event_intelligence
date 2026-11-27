/**
 * Lightweight grid clustering for globe pins.
 *
 * Dense regions would otherwise paint dozens of overlapping points. Pins that
 * fall into the same grid cell are merged into one cluster point whose
 * position is the *average of the reported coordinates* — a display device,
 * disclosed in the cluster label and panel, never stored and never presented
 * as an event location. Country aggregates are not clustered here (they are
 * already aggregates); callers pass only true pins.
 */

export const DEFAULT_CLUSTER_CELL_DEGREES = 5;

function cellKey(latitude, longitude, cellDegrees) {
  return `${Math.floor(latitude / cellDegrees)}:${Math.floor(longitude / cellDegrees)}`;
}

/**
 * @param {Array} points plottable events (must have numeric lat/lng)
 * @param {{cellDegrees?: number}} [options]
 * @returns {Array} points + cluster points (`is_cluster: true`, with
 *   `cluster_count` and the member `events`)
 */
export function clusterMapPoints(points, options = {}) {
  const cellDegrees = options.cellDegrees || DEFAULT_CLUSTER_CELL_DEGREES;
  const pins = (points || []).filter(
    (point) =>
      !point.is_country_aggregate &&
      Number.isFinite(Number(point.latitude)) &&
      Number.isFinite(Number(point.longitude))
  );
  if (pins.length < 2) return [...pins];

  const cells = new Map();
  for (const pin of pins) {
    const key = cellKey(Number(pin.latitude), Number(pin.longitude), cellDegrees);
    if (!cells.has(key)) cells.set(key, []);
    cells.get(key).push(pin);
  }

  const result = [];
  for (const [key, members] of cells.entries()) {
    if (members.length === 1) {
      result.push(members[0]);
      continue;
    }
    const latitude =
      members.reduce((sum, event) => sum + Number(event.latitude), 0) / members.length;
    const longitude =
      members.reduce((sum, event) => sum + Number(event.longitude), 0) / members.length;
    const importance = Math.max(
      ...members.map((event) => Number(event.importance ?? event.severity ?? 0) || 0)
    );
    const names = [...new Set(members.map((event) => event.country).filter(Boolean))];
    result.push({
      id: `map-cluster-${key}`,
      title: `${members.length} events clustered in this area`,
      country: names.length === 1 ? names[0] : names.length > 1 ? "Multiple countries" : "Global",
      latitude,
      longitude,
      importance,
      is_cluster: true,
      cluster_count: members.length,
      member_ids: members.map((event) => event.id),
      events: members,
    });
  }
  return result;
}
