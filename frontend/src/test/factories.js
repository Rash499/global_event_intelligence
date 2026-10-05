export const makeEvent = (overrides = {}) => ({
  id: 1,
  title: "Earthquake strikes coastal region",
  summary: "A strong earthquake was recorded.",
  category: "natural_disaster",
  country: "Japan",
  country_code: "JP",
  latitude: 35.6,
  longitude: 139.7,
  importance: 9,
  confidence: 0.82,
  event_time: new Date().toISOString(),
  ...overrides,
});

export const hoursAgo = (hours) => new Date(Date.now() - hours * 3600 * 1000).toISOString();
export const daysAgo = (days) => hoursAgo(days * 24);
