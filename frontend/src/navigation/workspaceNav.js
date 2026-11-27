/**
 * Workspace navigation model.
 *
 * The app is an operations workspace: a small set of top-level sections, with
 * detail screens layered on top of a section (event investigation, country
 * risk, weather brief). Keeping this as a pure reducer means the navigation
 * rules are unit-testable and the shell never grows ad-hoc `if` chains.
 *
 * Sections
 *   overview    live globe + latest signals (home)
 *   events      paginated event search / queue
 *   investigation  single event evidence view
 *   countries   country risk + comparison
 *   map         dedicated map workspace (globe or weather layers)
 *   weather     weather layer of the map workspace + brief
 *   alerts      alert centre (rules + triggered alerts)
 *   providers   provider health / collection runs
 *   reports     generated intelligence reports + export
 *   system      system status, configuration and data quality
 *   historical  historical explorer
 *   assistant   AI assistant (existing feature, kept as-is)
 *   dashboard   analytics dashboard (existing feature, kept as-is)
 */

export const workspaceSections = [
  { id: "overview", label: "Overview", icon: "◎", group: "Monitor" },
  { id: "map", label: "Map", icon: "◍", group: "Monitor" },
  { id: "events", label: "Events", icon: "≡", group: "Monitor" },
  { id: "alerts", label: "Alerts", icon: "⚠", group: "Monitor" },
  { id: "countries", label: "Countries", icon: "◭", group: "Analyse" },
  { id: "entities", label: "Entities", icon: "◇", group: "Analyse" },
  { id: "historical", label: "History", icon: "⏱", group: "Analyse" },
  { id: "reports", label: "Reports", icon: "▤", group: "Deliver" },
  { id: "assistant", label: "Assistant", icon: "✦", group: "Deliver" },
  { id: "providers", label: "Providers", icon: "⇉", group: "Operate" },
  { id: "system", label: "System", icon: "⚙", group: "Operate" },
];

/** Sections whose primary surface is the globe/weather map. */
const MAP_SECTIONS = new Set(["overview", "map", "weather"]);

export const initialNavState = {
  page: "overview",
  mode: "events",
  selectedEvent: null,
  selectedEventId: null,
  selectedCountry: null,
  selectedWeather: null,
  /** Pre-applied filters when jumping from a search result into a section. */
  pendingFilters: null,
};

const cleared = {
  selectedEvent: null,
  selectedEventId: null,
  selectedCountry: null,
  selectedWeather: null,
  pendingFilters: null,
};

const SECTION_PAGES = new Set([
  ...workspaceSections.map((section) => section.id),
  "dashboard",
]);

export function navReducer(state, action) {
  switch (action.type) {
    case "navigate": {
      const page = SECTION_PAGES.has(action.page) ? action.page : "overview";
      const mode =
        page === "weather" ? "weather" : page === "map" ? state.mode : "events";
      return {
        ...state,
        ...cleared,
        page: page === "weather" ? "map" : page,
        mode: page === "map" || page === "overview" ? mode : "events",
        pendingFilters: action.filters || null,
      };
    }
    case "overview":
      return { ...state, ...cleared, page: "overview", mode: "events" };
    case "dashboard":
      return { ...state, ...cleared, page: "dashboard" };
    // Kept for backwards compatibility with existing callers/tests.
    case "weather":
      return { ...state, ...cleared, page: "overview", mode: "weather" };
    case "historical":
      return { ...state, ...cleared, page: "historical", mode: "events" };
    case "assistant":
      return { ...state, ...cleared, page: "assistant" };
    case "setMode":
      return { ...state, ...cleared, page: "overview", mode: action.mode };
    case "selectEvent":
      return {
        ...state,
        selectedEvent: action.event,
        selectedEventId: action.event?.id ?? null,
        selectedCountry: null,
      };
    case "clearEvent":
      return { ...state, selectedEvent: null, selectedEventId: null };
    case "selectCountry":
      return {
        ...state,
        selectedEvent: null,
        selectedEventId: null,
        selectedCountry: action.country,
      };
    case "selectWeather":
      return { ...state, selectedWeather: action.weather };
    case "clearWeather":
      return { ...state, selectedWeather: null };
    default:
      return state;
  }
}

/** Which top-level navigation item should read as active. */
export function deriveActiveView(state) {
  if (MAP_SECTIONS.has(state.page)) {
    if (state.mode === "weather" || state.selectedWeather) return "map";
    return state.page === "overview" ? "overview" : "map";
  }
  if (state.page === "dashboard") return "overview";
  return state.page;
}

export function deriveScreen(state) {
  if (state.selectedCountry) return "country";
  if (state.selectedWeather) return "weather-detail";
  if (state.page === "dashboard") return "dashboard";
  if (state.selectedEvent || state.selectedEventId) return "event";
  return state.page;
}

/** True when the shell should render the globe surface. */
export function isMapScreen(state) {
  return deriveScreen(state) === "overview" || deriveScreen(state) === "map";
}
