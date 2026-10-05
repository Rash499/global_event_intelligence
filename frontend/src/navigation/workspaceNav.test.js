import { describe, expect, it } from "vitest";
import { deriveActiveView, deriveScreen, initialNavState, navReducer } from "./workspaceNav";

const reduce = (actions) => actions.reduce(navReducer, initialNavState);

describe("workspaceNav", () => {
  it("starts at overview/events", () => {
    expect(deriveScreen(initialNavState)).toBe("overview");
    expect(deriveActiveView(initialNavState)).toBe("overview");
  });
  it("handles top-level navigation", () => {
    const state = reduce([{type:"dashboard"}]);
    expect(deriveScreen(state)).toBe("dashboard");
    expect(deriveActiveView(state)).toBe("dashboard");
  });
  it("handles weather mode and detail", () => {
    const weather=reduce([{type:"weather"}]);
    expect(deriveScreen(weather)).toBe("overview");
    expect(deriveActiveView(weather)).toBe("weather");
    const detail=navReducer(weather,{type:"selectWeather",weather:{country_code:"JP"}});
    expect(deriveScreen(detail)).toBe("weather-detail");
  });
  it("gives selections precedence", () => {
    const event={id:1}; const country={code:"JP"};
    let state=navReducer(initialNavState,{type:"selectEvent",event});
    expect(deriveScreen(state)).toBe("event");
    state=navReducer(state,{type:"selectCountry",country});
    expect(deriveScreen(state)).toBe("country");
  });
});
