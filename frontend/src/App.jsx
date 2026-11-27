import { lazy, Suspense, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import AlertToast from "./components/AlertToast";
import AuthLanding from "./components/auth/AuthLanding";
import { useAuth } from "./components/auth/AuthContext";
import { InteractionProvider } from "./components/interactions/InteractionProvider";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import PageTransition from "./components/ui/PageTransition";
import CommandPalette from "./components/workspace/CommandPalette";
import { ViewFallback } from "./components/ui/Skeleton";
import OverviewView from "./components/workspace/OverviewView";
import MapView from "./components/workspace/MapView";
import { deriveActiveView, deriveScreen, initialNavState, navReducer } from "./navigation/workspaceNav";
import { getEvent, getGlobalWeather, getProviders, getAlerts, runIngestion } from "./services/api.jsx";
import { loadWorldGeoJSON } from "./services/worldGeoJson.jsx";

const EventInvestigation = lazy(() => import("./components/workspace/EventInvestigation"));
const EventsView = lazy(() => import("./components/workspace/EventsView"));
const CountriesView = lazy(() => import("./components/workspace/CountriesView"));
const EntitiesView = lazy(() => import("./components/workspace/EntitiesView"));
const AlertsView = lazy(() => import("./components/workspace/AlertsView"));
const ProvidersView = lazy(() => import("./components/workspace/ProvidersView"));
const ReportsView = lazy(() => import("./components/workspace/ReportsView"));
const SystemView = lazy(() => import("./components/workspace/SystemView"));
const CountryDashboard = lazy(() => import("./components/CountryDashboard"));
const GlobalEventDashboard = lazy(() => import("./components/GlobalEventDashboard"));
const HistoricalIntelligenceDashboard = lazy(() => import("./components/HistoricalIntelligenceDashboard"));
const WeatherDashboard = lazy(() => import("./components/weather/WeatherDashboard"));
const CountryMiniMap = lazy(() => import("./components/weather/CountryMiniMap"));
const GlobalIntelligenceAssistant = lazy(() => import("./components/assistant/GlobalIntelligenceAssistant"));

function getCountryCode(feature) {
  const candidates = [feature.properties?.ISO_A2, feature.properties?.ISO_A2_E];
  return candidates.find((code) => typeof code === "string" && /^[A-Z]{2,3}$/.test(code)) || null;
}
function getCountryName(feature) {
  return feature.properties?.NAME || feature.properties?.ADMIN || "Unknown";
}
function getBoundingBoxCenter(feature) {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) return null;
  const points = [];
  const collect = (value) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && Number.isFinite(value[0]) && Number.isFinite(value[1])) {
      points.push(value);
      return;
    }
    value.forEach(collect);
  };
  collect(coordinates);
  if (!points.length) return null;
  const longitudes = points.map((point) => point[0]);
  const latitudes = points.map((point) => point[1]);
  return {
    latitude: (Math.min(...latitudes) + Math.max(...latitudes)) / 2,
    longitude: (Math.min(...longitudes) + Math.max(...longitudes)) / 2,
  };
}

/**
 * Weather needs anchor points per country. These are the geometric centres of
 * the loaded country polygons — used only to ask a weather API for a country's
 * conditions, never to represent where an *event* happened.
 */
async function loadWeatherLocations() {
  const geojson = await loadWorldGeoJSON();
  return (geojson.features || [])
    .map((feature) => {
      const code = getCountryCode(feature);
      const center = getBoundingBoxCenter(feature);
      if (!code || !center) return null;
      return { country_code: code, country: getCountryName(feature), ...center };
    })
    .filter(Boolean);
}

function IntelligenceWorkspace({ user, onLogout }) {
  const [nav, dispatch] = useReducer(navReducer, initialNavState);
  const { mode, selectedCountry, selectedWeather, selectedEventId, page } = nav;

  const [weather, setWeather] = useState([]);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [weatherError, setWeatherError] = useState("");
  const [collecting, setCollecting] = useState(false);
  const [status, setStatus] = useState("");
  const [eventAlert, setEventAlert] = useState("");
  const [providerHealth, setProviderHealth] = useState(null);
  const [alertCount, setAlertCount] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [pendingEvent, setPendingEvent] = useState(null);
  const automaticCollectionStarted = useRef(false);

  const loadWeather = useCallback(async () => {
    if (weather.length) return;
    setWeatherLoading(true);
    setWeatherError("");
    try {
      const locations = await loadWeatherLocations();
      const data = await getGlobalWeather(locations);
      setWeather(data.locations || []);
    } catch (error) {
      console.error("Failed to load global weather:", error);
      setWeatherError("Weather data could not be loaded. Check the FastAPI weather endpoint and world.geojson.");
    } finally {
      setWeatherLoading(false);
    }
  }, [weather.length]);

  useEffect(() => {
    if (mode === "weather") loadWeather();
  }, [mode, loadWeather]);

  const refreshOperationalState = useCallback(async () => {
    try {
      const [providers, alerts] = await Promise.all([getProviders(), getAlerts("new")]);
      setProviderHealth(providers.by_status || null);
      setAlertCount((alerts.items || []).length);
    } catch (error) {
      // Health is advisory chrome: a failure here must not break the workspace.
      console.error("Provider/alert summary unavailable:", error);
      setProviderHealth(null);
    }
  }, []);

  useEffect(() => {
    refreshOperationalState();
    const timer = window.setInterval(refreshOperationalState, 120000);
    return () => window.clearInterval(timer);
  }, [refreshOperationalState]);

  useEffect(() => {
    if (automaticCollectionStarted.current) return;
    automaticCollectionStarted.current = true;
    refreshOperationalState();
  }, [refreshOperationalState]);

  // Ctrl/Cmd-K opens the command palette from anywhere in the workspace.
  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const collectEvents = useCallback(async () => {
    setCollecting(true);
    setStatus("Collecting from configured providers…");
    try {
      const result = await runIngestion();
      const count = Number(result?.events_created) || 0;
      const failures = (result?.providers || []).filter(
        (provider) => provider.status && !["healthy", "idle"].includes(provider.status)
      );
      if (count > 0) setEventAlert(`${count} new ${count === 1 ? "event" : "events"} detected`);
      setStatus(
        count
          ? `Collection complete: ${count} ${count === 1 ? "event" : "events"} added.`
          : "Collection completed. No new events were created."
      );
      if (failures.length) {
        setStatus(
          (previous) =>
            `${previous} ${failures.length} provider(s) reported problems — see Providers for details.`
        );
      }
      await refreshOperationalState();
    } catch (error) {
      console.error(error);
      const detail = error?.response?.data?.detail;
      setStatus(detail || "Collection failed. Check the backend logs and provider health.");
    } finally {
      setCollecting(false);
    }
  }, [refreshOperationalState]);

  const handleCountrySelect = (country) => {
    if (mode === "weather") {
      const item = weather.find((entry) => entry.country_code === (country.code || country.country_code));
      if (item) dispatch({ type: "selectWeather", weather: item });
      return;
    }
    dispatch({ type: "selectCountry", country });
  };

  const openEvent = useCallback(async (payload) => {
    const id = typeof payload === "number" ? payload : payload?.id;
    if (!id) return;
    if (payload?.event) {
      dispatch({ type: "selectEvent", event: payload.event });
      return;
    }
    // Navigation needs an id even before the detail request resolves, so the
    // shell renders the investigation view with its own loading state.
    dispatch({ type: "selectEvent", event: { id } });
    try {
      const full = await getEvent(id);
      setPendingEvent(full);
    } catch (error) {
      console.error("Could not prefetch event", id, error);
    }
  }, []);

  const navigate = useCallback((target, context = {}) => {
    if (target === "country" || (context.country && target === "countries")) {
      const code = context.country || context.code;
      dispatch({ type: "selectCountry", country: { code, name: context.name } });
      return;
    }
    if (target === "event" && context.id) {
      openEvent({ id: context.id });
      return;
    }
    dispatch({ type: "navigate", page: target, filters: context });
  }, [openEvent]);

  const screen = deriveScreen(nav);
  const activeView = deriveActiveView(nav);
  const selectedEvent = nav.selectedEvent;

  const chrome = (content) => (
    <>
      <Navbar
        activeView={activeView}
        onNavigate={navigate}
        onOverview={() => dispatch({ type: "overview" })}
        onOpenSearch={() => setPaletteOpen(true)}
        onCollect={collectEvents}
        collecting={collecting}
        providerHealth={providerHealth}
        alertCount={alertCount}
        user={user}
        onLogout={onLogout}
      />
      <PageTransition viewKey={screen}>
        <Suspense fallback={<ViewFallback />}>{content}</Suspense>
      </PageTransition>
      <Footer />
    </>
  );

  const body = useMemo(() => {
    switch (screen) {
      case "country":
        return (
          <main className="app app-page">
            <CountriesView
              initialSelection={{ country: selectedCountry?.code, name: selectedCountry?.name }}
              onSelectEvent={openEvent}
            />
          </main>
        );
      case "weather-detail":
        return (
          <main className="app-page weather-brief-page">
            <WeatherDashboard
              weather={selectedWeather}
              weatherList={weather}
              miniMap={<CountryMiniMap weather={selectedWeather} />}
              onBack={() => dispatch({ type: "clearWeather" })}
              onSelect={(item) => dispatch({ type: "selectWeather", weather: item })}
            />
          </main>
        );
      case "event":
        return (
          <main className="app app-page">
            <EventInvestigation
              eventId={selectedEvent?.id || selectedEventId || pendingEvent?.id}
              initialEvent={selectedEvent?.title ? { ...selectedEvent, ...pendingEvent } : pendingEvent}
              onBack={() => dispatch({ type: "clearEvent" })}
              onSelectEvent={(event) => openEvent(event)}
              onOpenCountry={(country) => dispatch({ type: "selectCountry", country })}
            />
          </main>
        );
      case "events":
        return (
          <main className="app app-page">
            <EventsView
              initialFilters={nav.pendingFilters}
              onSelectEvent={openEvent}
              onNavigate={navigate}
            />
          </main>
        );
      case "map":
        return (
          <main className="app app-page">
            <MapView
              mode={mode}
              onModeChange={(next) => dispatch({ type: "setMode", mode: next })}
              onSelectEvent={openEvent}
              onSelectCountry={handleCountrySelect}
              weather={weather}
              weatherLoading={weatherLoading}
              onSelectWeather={(item) => dispatch({ type: "selectWeather", weather: item })}
              selectedCountryCode={selectedCountry?.code}
              initialFilters={nav.pendingFilters}
            />
          </main>
        );
      case "entities":
        return (
          <main className="app app-page">
            <EntitiesView initialSelection={nav.pendingFilters} onSelectEvent={openEvent} />
          </main>
        );
      case "alerts":
        return (
          <main className="app app-page">
            <AlertsView onSelectEvent={openEvent} />
          </main>
        );
      case "providers":
        return (
          <main className="app app-page">
            <ProvidersView />
          </main>
        );
      case "reports":
        return (
          <main className="app app-page">
            <ReportsView onSelectEvent={openEvent} />
          </main>
        );
      case "system":
        return (
          <main className="app app-page">
            <SystemView />
          </main>
        );
      case "historical":
        return (
          <main className="app app-page">
            <HistoricalIntelligenceDashboard onBack={() => dispatch({ type: "overview" })} />
          </main>
        );
      case "assistant":
        return (
          <main className="app app-page">
            <GlobalIntelligenceAssistant onBack={() => dispatch({ type: "overview" })} />
          </main>
        );
      case "dashboard":
        return (
          <main className="app app-page">
            <GlobalEventDashboard events={[]} />
          </main>
        );
      case "overview":
      default:
        return (
          <main className="app app-page">
            <OverviewView onSelectEvent={openEvent} onNavigate={navigate} />
            <MapView
              mode={mode}
              onModeChange={(next) => dispatch({ type: "setMode", mode: next })}
              onSelectEvent={openEvent}
              onSelectCountry={handleCountrySelect}
              weather={weather}
              weatherLoading={weatherLoading}
              onSelectWeather={(item) => dispatch({ type: "selectWeather", weather: item })}
              selectedCountryCode={selectedCountry?.code}
            />
          </main>
        );
    }
  }, [
    screen, mode, weather, weatherLoading, selectedCountry, selectedEvent, selectedEventId,
    pendingEvent, nav.pendingFilters, openEvent, navigate, handleCountrySelect,
  ]);

  return (
    <>
      {chrome(body)}
      {status && (
        <div className="notice ws-floating-notice" role="status" aria-live="polite">
          {status}
          <button type="button" className="ws-icon-button" onClick={() => setStatus("")} aria-label="Dismiss status">×</button>
        </div>
      )}
      <AlertToast message={eventAlert} onDismiss={() => setEventAlert("")} />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={navigate}
        onOpenEvent={(event) => openEvent(event)}
        onOpenCountry={(country) => dispatch({ type: "selectCountry", country })}
      />
    </>
  );
}

export default function App() {
  const { user, loading, logout } = useAuth();
  if (loading) return <main className="auth-loading" role="status">Restoring your session...</main>;
  if (!user) return <AuthLanding />;
  return (
    <InteractionProvider key={user.id}>
      <IntelligenceWorkspace user={user} onLogout={logout} />
    </InteractionProvider>
  );
}
