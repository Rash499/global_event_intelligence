import { lazy, Suspense, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import Globe from "./components/Globe";
import AlertToast from "./components/AlertToast";
import AuthLanding from "./components/auth/AuthLanding";
import { useAuth } from "./components/auth/AuthContext";
import { InteractionProvider } from "./components/interactions/InteractionProvider";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import StatsBar from "./components/StatsBar";
import CategoryFilter from "./components/CategoryFilter";
import EventList from "./components/EventList";
import WeatherModeToggle from "./components/weather/WeatherModeToggle";
import WeatherPanel from "./components/weather/WeatherPanel";
import HeroBackdrop from "./components/ui/HeroBackdrop";
import PageTransition from "./components/ui/PageTransition";
import { ViewFallback } from "./components/ui/Skeleton";
import { deriveActiveView, deriveScreen, initialNavState, navReducer } from "./navigation/workspaceNav";
import { getEventHistory, getGlobalWeather, runIngestion } from "./services/api.jsx";
import { loadWorldGeoJSON } from "./services/worldGeoJson.jsx";

const EventDetails = lazy(() => import("./components/EventDetails"));
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
function getCountryName(feature) { return feature.properties?.NAME || feature.properties?.ADMIN || "Unknown"; }
function getBoundingBoxCenter(feature) {
  const coordinates = feature.geometry?.coordinates; if (!coordinates) return null;
  const points = [];
  const collect = (value) => { if (!Array.isArray(value)) return; if (value.length >= 2 && Number.isFinite(value[0]) && Number.isFinite(value[1])) { points.push(value); return; } value.forEach(collect); };
  collect(coordinates); if (!points.length) return null;
  const longitudes = points.map((point) => point[0]); const latitudes = points.map((point) => point[1]);
  return { latitude: (Math.min(...latitudes) + Math.max(...latitudes)) / 2, longitude: (Math.min(...longitudes) + Math.max(...longitudes)) / 2 };
}
async function loadWeatherLocations() {
  const geojson = await loadWorldGeoJSON();
  return (geojson.features || []).map((feature) => { const code = getCountryCode(feature); const center = getBoundingBoxCenter(feature); if (!code || !center) return null; return { country_code: code, country: getCountryName(feature), ...center }; }).filter(Boolean);
}

function IntelligenceWorkspace({ user, onLogout }) {
  const [nav, dispatch] = useReducer(navReducer, initialNavState);
  const { mode, selectedEvent, selectedCountry, selectedWeather } = nav;
  const [events, setEvents] = useState([]); const [category, setCategory] = useState("all"); const [weather, setWeather] = useState([]);
  const [weatherLoading, setWeatherLoading] = useState(false); const [weatherError, setWeatherError] = useState(""); const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false); const [status, setStatus] = useState(""); const [eventAlert, setEventAlert] = useState(""); const automaticCollectionStarted = useRef(false);
  // Latest Events is a rolling 24-hour view. Historical Intelligence keeps
  // access to older events separately.
  const recentEvents = events.filter((event) => { const eventDate = new Date(event.event_time); const now = Date.now(); const lookbackMs = 24 * 60 * 60 * 1000; return !Number.isNaN(eventDate.getTime()) && eventDate.getTime() >= now - lookbackMs && eventDate.getTime() <= now; });
  const loadEvents = useCallback(async () => { setLoading(true); try { setEvents(await getEventHistory(1000)); setStatus(""); } catch (error) { console.error(error); setStatus("Backend is not running. Start FastAPI on port 8000."); } finally { setLoading(false); } }, []);
  const loadWeather = useCallback(async () => { if (weather.length) return; setWeatherLoading(true); setWeatherError(""); try { const locations = await loadWeatherLocations(); const data = await getGlobalWeather(locations); setWeather(data.locations || []); } catch (error) { console.error("Failed to load global weather:", error); setWeatherError("Weather data could not be loaded. Check the FastAPI weather endpoint and world.geojson."); } finally { setWeatherLoading(false); } }, [weather.length]);
  useEffect(() => { if (mode === "weather") loadWeather(); }, [mode, loadWeather]);
  useEffect(() => { const refreshEvents = async () => { try { setEvents(await getEventHistory(1000)); } catch (error) { console.error("Failed to refresh the event feed:", error); } }; const timer = window.setInterval(refreshEvents, 60000); return () => window.clearInterval(timer); }, []);
  const collectEvents = useCallback(async (automatic = false) => { setCollecting(true); setStatus(automatic ? "Checking for new global events..." : "Collecting latest global news..."); try { const result = await runIngestion(); await loadEvents(); const count = Number(result?.events_created) || 0; if (count > 0) setEventAlert(count + " new " + (count === 1 ? "event" : "events") + " detected"); setStatus(count ? "New events detected: " + count + " " + (count === 1 ? "event" : "events") + " added." : "Collection completed. No new events detected."); } catch (error) { console.error(error); const detail = error?.response?.data?.detail; setStatus(detail || (automatic ? "Automatic news collection failed. Check the backend logs." : "News collection failed. Check the backend logs.")); } finally { setCollecting(false); } }, [loadEvents]);
  const handleCollect = () => collectEvents(); const dismissEventAlert = useCallback(() => setEventAlert(""), []);
  useEffect(() => { if (automaticCollectionStarted.current) return; automaticCollectionStarted.current = true; loadEvents(); }, [collectEvents, loadEvents]);
  const filteredEvents = useMemo(() => category === "all" ? recentEvents : recentEvents.filter((event) => event.category === category), [category, lastWeekEvents]);
  const weatherByCode = useMemo(() => Object.fromEntries(weather.map((item) => [item.country_code, item])), [weather]);
  const handleCountrySelect = (country) => { if (mode === "weather") { const item = weatherByCode[country.code]; if (item) dispatch({ type: "selectWeather", weather: item }); return; } dispatch({ type: "selectCountry", country }); };
  const handleEventSelect = (event) => dispatch({ type: "selectEvent", event }); const handleWeatherSelect = (item) => dispatch({ type: "selectWeather", weather: item }); const handleModeChange = (nextMode) => dispatch({ type: "setMode", mode: nextMode });
  const goOverview = () => dispatch({ type: "overview" }); const goDashboard = () => dispatch({ type: "dashboard" }); const goWeather = () => dispatch({ type: "weather" }); const goAssistant = () => dispatch({ type: "assistant" });
  const activeView = deriveActiveView(nav); const screen = deriveScreen(nav);
  const chrome = (page) => (<><Navbar activeView={activeView} onOverview={goOverview} onDashboard={goDashboard} onWeather={goWeather} onAssistant={goAssistant} onCollect={handleCollect} collecting={collecting} user={user} onLogout={onLogout}/><PageTransition viewKey={screen}><Suspense fallback={<ViewFallback/>}>{page}</Suspense></PageTransition><Footer/></>);
  switch (screen) {
    case "country": return chrome(<main className="app app-page"><CountryDashboard country={selectedCountry} onBack={goOverview}/></main>);
    case "weather-detail": return chrome(<main className="app-page weather-brief-page"><WeatherDashboard weather={selectedWeather} weatherList={weather} miniMap={<CountryMiniMap weather={selectedWeather}/>} onBack={() => dispatch({type:"clearWeather"})} onSelect={handleWeatherSelect}/></main>);
    case "historical": return chrome(<main className="app app-page"><HistoricalIntelligenceDashboard onBack={goOverview}/></main>);
    case "assistant": return chrome(<main className="app app-page"><GlobalIntelligenceAssistant onBack={goOverview}/></main>);
    case "dashboard": return chrome(<main className="app app-page"><div className="dashboard-navigation"><button className="back-button" onClick={goOverview}>← Back to World Map</button></div><GlobalEventDashboard events={recentEvents}/></main>);
    case "event": return chrome(<main className="app app-page"><EventDetails event={selectedEvent} onBack={() => dispatch({type:"clearEvent"})}/></main>);
    default: break;
  }
  return chrome(<main className="app app-page"><AlertToast message={eventAlert} onDismiss={dismissEventAlert}/><section className="hero-header"><HeroBackdrop/><div className="hero-copy"><p className="eyebrow">GLOBAL EVENT INTELLIGENCE</p><h1>World Event Map</h1><p className="subtitle">Monitor important events, emerging signals and global conditions in one live workspace.</p></div><div className="hero-status"><span><i/> LIVE FEED</span><small>Multi-source monitoring · Global coverage</small></div></section><div className="mode-bar"><WeatherModeToggle mode={mode} onChange={handleModeChange}/>{mode === "events" ? <><button className="dashboard-button" onClick={goDashboard}>Open Global Event Dashboard</button><button className="assistant-nav-button" onClick={goAssistant}>✦ Global Intelligence Assistant</button></> : <div className="weather-source-note">Weather source: Open-Meteo · no API key</div>}</div>{mode === "events" ? <><StatsBar events={recentEvents}/><CategoryFilter selectedCategory={category} onChange={setCategory}/>{status && <div className="notice" role="status" aria-live="polite">{status}</div>}</> : <div className="weather-mode-header"><div><p className="eyebrow">GLOBAL WEATHER INTELLIGENCE</p><h2>Current conditions & future severity</h2><p>Areas are ranked using current weather and forecast variables. The score is an application index, not an official warning.</p></div>{weatherError && <div className="notice weather-error">{weatherError}</div>}</div>}<section className="workspace"><div className="map-panel"><Globe mode={mode} events={filteredEvents} weather={weather} onSelectEvent={handleEventSelect} onSelectWeather={handleWeatherSelect} onSelectCountry={handleCountrySelect} selectedCountryCode={selectedCountry?.code}/>{((mode === "events" && loading) || (mode === "weather" && weatherLoading)) && <div className="map-loading" role="status">{mode === "events" ? "Loading global events..." : "Loading global weather..."}</div>}</div>{mode === "events" ? <aside className="latest-panel"><div className="panel-header"><div><p className="eyebrow">LIVE INTELLIGENCE</p><h2>Latest Events</h2></div><span>{filteredEvents.length}</span></div><EventList events={filteredEvents.slice(0,15)} onSelect={handleEventSelect} variant="grid" loading={loading}/></aside> : <WeatherPanel weather={weather} onSelect={handleWeatherSelect} selectedCode={selectedWeather?.country_code}/>}</section></main>);
}
export default function App() { const { user, loading, logout } = useAuth(); if (loading) return <main className="auth-loading" role="status">Restoring your session...</main>; if (!user) return <AuthLanding/>; return <InteractionProvider key={user.id}><IntelligenceWorkspace user={user} onLogout={logout}/></InteractionProvider>; }
