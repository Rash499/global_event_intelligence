import { describe, expect, it } from "vitest";
import {
  deriveActiveView,
  deriveScreen,
  initialNavState,
  isMapScreen,
  navReducer,
  workspaceSections,
} from "./workspaceNav";

const reduce = (actions) => actions.reduce(navReducer, initialNavState);

describe("workspaceNav", () => {
  it("starts at overview/events", () => {
    expect(deriveScreen(initialNavState)).toBe("overview");
    expect(deriveActiveView(initialNavState)).toBe("overview");
    expect(isMapScreen(initialNavState)).toBe(true);
  });

  it("exposes the grouped operations sections with unique ids", () => {
    const ids = workspaceSections.map((section) => section.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(
      expect.arrayContaining(["overview", "map", "events", "alerts", "countries", "providers", "reports", "system"])
    );
  });

  it("navigates to every section and marks it active", () => {
    for (const section of workspaceSections) {
      const state = navReducer(initialNavState, { type: "navigate", page: section.id });
      expect(deriveScreen(state)).toBe(section.id === "weather" ? "map" : section.id);
      expect(deriveActiveView(state)).toBe(section.id === "weather" ? "map" : section.id);
    }
  });

  it("falls back to overview for an unknown section", () => {
    const state = navReducer(initialNavState, { type: "navigate", page: "does-not-exist" });
    expect(deriveScreen(state)).toBe("overview");
  });

  it("clears detail selections when changing section", () => {
    let state = navReducer(initialNavState, { type: "selectEvent", event: { id: 7 } });
    state = navReducer(state, { type: "navigate", page: "alerts" });
    expect(state.selectedEvent).toBeNull();
    expect(state.selectedEventId).toBeNull();
    expect(deriveScreen(state)).toBe("alerts");
  });

  it("keeps pending filters for the target section", () => {
    const state = navReducer(initialNavState, {
      type: "navigate",
      page: "events",
      filters: { category: "natural_disaster" },
    });
    expect(state.pendingFilters).toEqual({ category: "natural_disaster" });
    const cleared = navReducer(state, { type: "navigate", page: "system" });
    expect(cleared.pendingFilters).toBeNull();
  });

  it("handles the legacy dashboard page", () => {
    const state = reduce([{ type: "dashboard" }]);
    expect(deriveScreen(state)).toBe("dashboard");
    // Analytics has no top-level nav item any more; the overview entry stays active.
    expect(deriveActiveView(state)).toBe("overview");
  });

  it("handles weather mode and detail", () => {
    const weather = reduce([{ type: "weather" }]);
    expect(deriveScreen(weather)).toBe("overview");
    expect(deriveActiveView(weather)).toBe("map");
    expect(isMapScreen(weather)).toBe(true);
    const detail = navReducer(weather, { type: "selectWeather", weather: { country_code: "JP" } });
    expect(deriveScreen(detail)).toBe("weather-detail");
    expect(isMapScreen(detail)).toBe(false);
  });

  it("gives selections precedence", () => {
    const event = { id: 1 };
    const country = { code: "JP" };
    let state = navReducer(initialNavState, { type: "selectEvent", event });
    expect(deriveScreen(state)).toBe("event");
    expect(state.selectedEventId).toBe(1);
    state = navReducer(state, { type: "selectCountry", country });
    expect(deriveScreen(state)).toBe("country");
    expect(state.selectedEventId).toBeNull();
  });

  it("clears selections on request", () => {
    let state = navReducer(initialNavState, { type: "selectEvent", event: { id: 3 } });
    state = navReducer(state, { type: "clearEvent" });
    expect(deriveScreen(state)).toBe("overview");
    state = navReducer(state, { type: "selectWeather", weather: { country_code: "JP" } });
    state = navReducer(state, { type: "clearWeather" });
    expect(deriveScreen(state)).toBe("overview");
  });

  it("sets map mode explicitly", () => {
    const state = navReducer(initialNavState, { type: "setMode", mode: "weather" });
    expect(state.mode).toBe("weather");
    expect(deriveActiveView(state)).toBe("map");
  });
});
