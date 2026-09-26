import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Globe from "./components/Globe";
import AlertToast from "./components/AlertToast";
import Header from "./components/Header";
import StatsBar from "./components/StatsBar";
import CategoryFilter from "./components/CategoryFilter";
import EventList from "./components/EventList";
import EventDetails from "./components/EventDetails";
import CountryDashboard from "./components/CountryDashboard";
import GlobalEventDashboard from "./components/GlobalEventDashboard";
import WeatherModeToggle from "./components/weather/WeatherModeToggle";
import WeatherPanel from "./components/weather/WeatherPanel";
import WeatherDashboard from "./components/weather/WeatherDashboard";

import {
  getEventHistory,
  getGlobalWeather,
  runIngestion,
} from "./services/api.jsx";
import { getLocalUserId } from "./services/eventIdentity.jsx";
import { loadWorldGeoJSON } from "./services/worldGeoJson.jsx";

import "./styles/globals.css";
import "./styles/alerts.css";
import "./styles/globe.css";
import "./styles/dashboard.css";
import "./styles/components.css";
import "./styles/weather.css";

function getCountryCode(feature) {
  const candidates = [
    feature.properties?.ISO_A2,
    feature.properties?.ISO_A2_E,
  ];

  return (
    candidates.find(
      (code) => typeof code === "string" && /^[A-Z]{2,3}$/.test(code)
    ) || null
  );
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

async function loadWeatherLocations() {
  const geojson = await loadWorldGeoJSON();

  return (geojson.features || [])
    .map((feature) => {
      const code = getCountryCode(feature);
      const center = getBoundingBoxCenter(feature);
      if (!code || !center) return null;

      return {
        country_code: code,
        country: getCountryName(feature),
        ...center,
      };
    })
    .filter(Boolean);
}

export default function App() {
  const [events, setEvents] = useState([]);
  const [category, setCategory] = useState("all");
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [selectedCountry, setSelectedCountry] = useState(null);
  const [selectedWeather, setSelectedWeather] = useState(null);
  const [showGlobalDashboard, setShowGlobalDashboard] = useState(false);
  const [mode, setMode] = useState("events");
  const [weather, setWeather] = useState([]);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [weatherError, setWeatherError] = useState("");
  const [loading, setLoading] = useState(true);
  const [collecting, setCollecting] = useState(false);
  const [status, setStatus] = useState("");
  const [eventAlert, setEventAlert] = useState("");
  const automaticCollectionStarted = useRef(false);

  const lastWeekEvents = events.filter((event) => {
    const eventDate = new Date(event.event_time);
    const now = Date.now();
    const oneWeekAgo = now - 7 * 24 * 60 * 60 * 1000;

    return (
      !Number.isNaN(eventDate.getTime()) &&
      eventDate.getTime() >= oneWeekAgo &&
      eventDate.getTime() <= now
    );
  });

  const loadEvents = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getEventHistory(1000, getLocalUserId());
      setEvents(data);
      setStatus("");
    } catch (error) {
      console.error(error);
      setStatus("Backend is not running. Start FastAPI on port 8000.");
    } finally {
      setLoading(false);
    }
  }, []);

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
      setWeatherError(
        "Weather data could not be loaded. Check the FastAPI weather endpoint and world.geojson."
      );
    } finally {
      setWeatherLoading(false);
    }
  }, [weather.length]);

  useEffect(() => {
    if (mode === "weather") loadWeather();
  }, [mode, loadWeather]);

  const collectEvents = useCallback(async (automatic = false) => {
    setCollecting(true);
    setStatus(
      automatic ? "Checking for new global events..." : "Collecting latest global news..."
    );

    try {
      const result = await runIngestion();
      await loadEvents();
      const newEventCount = Number(result?.events_created) || 0;
      if (newEventCount > 0) {
        setEventAlert(
          `${newEventCount} new ${newEventCount === 1 ? "event" : "events"} detected`
        );
      }
      setStatus(
        newEventCount
          ? `New events detected: ${newEventCount} ${newEventCount === 1 ? "event" : "events"} added.`
          : "Collection completed. No new events detected."
      );
    } catch (error) {
      console.error(error);
      setStatus(
        automatic
          ? "Automatic news collection failed. Check the backend connection."
          : "News collection failed. Check the backend connection."
      );
    } finally {
      setCollecting(false);
    }
  }, [loadEvents]);

  const handleCollect = () => collectEvents();
  const dismissEventAlert = useCallback(() => setEventAlert(""), []);

  useEffect(() => {
    if (automaticCollectionStarted.current) return;
    automaticCollectionStarted.current = true;

    const initializeFeed = async () => {
      await loadEvents();
      await collectEvents(true);
    };

    initializeFeed();
  }, [collectEvents, loadEvents]);

  const filteredEvents = useMemo(
    () =>
      category === "all"
        ? lastWeekEvents
        : lastWeekEvents.filter((event) => event.category === category),
    [category, lastWeekEvents]
  );

  const weatherByCode = useMemo(
    () => Object.fromEntries(weather.map((item) => [item.country_code, item])),
    [weather]
  );

  const handleCountrySelect = (country) => {
    if (mode === "weather") {
      const item = weatherByCode[country.code];
      if (item) setSelectedWeather(item);
      return;
    }

    setSelectedEvent(null);
    setSelectedCountry(country);
  };

  const handleEventSelect = (event) => {
    setSelectedEvent(event);
    setSelectedCountry(null);
  };

  const handleWeatherSelect = (item) => {
    setSelectedWeather(item);
  };

  const handleModeChange = (nextMode) => {
    setSelectedEvent(null);
    setSelectedCountry(null);
    setSelectedWeather(null);
    setShowGlobalDashboard(false);
    setMode(nextMode);
  };

  if (selectedCountry) {
    return (
      <main className="app">
        <CountryDashboard country={selectedCountry} onBack={() => setSelectedCountry(null)} />
      </main>
    );
  }

  if (selectedWeather) {
    return (
      <main className="app">
        <WeatherDashboard weather={selectedWeather} onBack={() => setSelectedWeather(null)} />
      </main>
    );
  }

  if (showGlobalDashboard) {
    return (
      <main className="app">
        <div className="dashboard-navigation">
          <button className="back-button" onClick={() => setShowGlobalDashboard(false)}>
            ← Back to World Map
          </button>
        </div>
        <GlobalEventDashboard events={events} />
      </main>
    );
  }

  if (selectedEvent) {
    return (
      <main className="app">
        <EventDetails event={selectedEvent} onBack={() => setSelectedEvent(null)} />
      </main>
    );
  }

  return (
    <main className="app">
      <AlertToast message={eventAlert} onDismiss={dismissEventAlert} />
      <Header onCollect={handleCollect} loading={collecting} />

      <div className="mode-bar">
        <WeatherModeToggle mode={mode} onChange={handleModeChange} />
        {mode === "events" ? (
          <button className="dashboard-button" onClick={() => setShowGlobalDashboard(true)}>
            Open Global Event Dashboard
          </button>
        ) : (
          <div className="weather-source-note">Weather source: Open-Meteo · no API key</div>
        )}
      </div>

      {mode === "events" ? (
        <>
          <StatsBar events={lastWeekEvents} />
          <CategoryFilter selectedCategory={category} onChange={setCategory} />
          {status && (
            <div className="notice" role="status" aria-live="polite">
              {status}
            </div>
          )}
        </>
      ) : (
        <div className="weather-mode-header">
          <div>
            <p className="eyebrow">GLOBAL WEATHER INTELLIGENCE</p>
            <h2>Current conditions & future severity</h2>
            <p>
              Areas are ranked using current weather and forecast variables. The score is an application index, not an official warning.
            </p>
          </div>
          {weatherError && <div className="notice weather-error">{weatherError}</div>}
        </div>
      )}

      <section className="workspace">
        <div className="map-panel">
          <Globe
            mode={mode}
            events={filteredEvents}
            weather={weather}
            onSelectEvent={handleEventSelect}
            onSelectWeather={handleWeatherSelect}
            onSelectCountry={handleCountrySelect}
            selectedCountryCode={selectedCountry?.code}
          />
          {((mode === "events" && loading) || (mode === "weather" && weatherLoading)) && (
            <div className="map-loading" role="status">
              {mode === "events" ? "Loading global events..." : "Loading global weather..."}
            </div>
          )}
        </div>

        {mode === "events" ? (
          <aside className="latest-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">LIVE INTELLIGENCE</p>
                <h2>Latest Events</h2>
              </div>
              <span>{filteredEvents.length}</span>
            </div>
            <EventList
              events={filteredEvents.slice(0, 15)}
              onSelect={handleEventSelect}
              variant="grid"
            />
          </aside>
        ) : (
          <WeatherPanel weather={weather} onSelect={handleWeatherSelect} />
        )}
      </section>
    </main>
  );
}
