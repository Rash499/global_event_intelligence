export const initialNavState = {
  page: "overview",
  mode: "events",
  selectedEvent: null,
  selectedCountry: null,
  selectedWeather: null,
};

const cleared = { selectedEvent: null, selectedCountry: null, selectedWeather: null };

export function navReducer(state, action) {
  switch (action.type) {
    case "overview": return { ...state, ...cleared, page: "overview", mode: "events" };
    case "dashboard": return { ...state, ...cleared, page: "dashboard" };
    case "weather": return { ...state, ...cleared, page: "overview", mode: "weather" };
    case "historical": return { ...state, ...cleared, page: "historical", mode: "events" };
    case "assistant": return { ...state, ...cleared, page: "assistant" };
    case "setMode": return { ...state, ...cleared, page: "overview", mode: action.mode };
    case "selectEvent": return { ...state, selectedEvent: action.event, selectedCountry: null };
    case "clearEvent": return { ...state, selectedEvent: null };
    case "selectCountry": return { ...state, selectedEvent: null, selectedCountry: action.country };
    case "selectWeather": return { ...state, selectedWeather: action.weather };
    case "clearWeather": return { ...state, selectedWeather: null };
    default: return state;
  }
}

export function deriveActiveView(state) {
  if (state.page === "assistant") return "assistant";
  if (state.page === "historical" || state.page === "dashboard") return "dashboard";
  if (state.mode === "weather" || state.selectedWeather) return "weather";
  return "overview";
}

export function deriveScreen(state) {
  if (state.selectedCountry) return "country";
  if (state.selectedWeather) return "weather-detail";
  if (state.page === "historical") return "historical";
  if (state.page === "assistant") return "assistant";
  if (state.page === "dashboard") return "dashboard";
  if (state.selectedEvent) return "event";
  return "overview";
}
