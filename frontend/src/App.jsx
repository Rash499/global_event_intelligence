import {
  useCallback,
  useEffect,
  useState,
} from "react";

import Globe from "./components/Globe";
import Header from "./components/Header";
import StatsBar from "./components/StatsBar";
import CategoryFilter from "./components/CategoryFilter";
import EventList from "./components/EventList";
import EventDetails from "./components/EventDetails";
import CountryDashboard from "./components/CountryDashboard";
import GlobalEventDashboard from "./components/GlobalEventDashboard";

import {
  getLatestEvents,
  runIngestion,
} from "./services/api";

import "./styles/globals.css";
import "./styles/globe.css";
import "./styles/dashboard.css";
import "./styles/components.css";

export default function App() {
  const [events, setEvents] =
    useState([]);

  const [category, setCategory] =
    useState("all");

  const [selectedEvent, setSelectedEvent] =
    useState(null);

  const [selectedCountry, setSelectedCountry] =
    useState(null);

  const [showGlobalDashboard, setShowGlobalDashboard] =
    useState(false);

  const [loading, setLoading] =
    useState(true);

  const [collecting, setCollecting] =
    useState(false);

  const [status, setStatus] =
    useState("");

  /*
   * Load events
   */
  const loadEvents = useCallback(
    async () => {
      setLoading(true);

      try {
        const data =
          await getLatestEvents(300);

        setEvents(data);
        setStatus("");
      } catch (error) {
        console.error(error);

        setStatus(
          "Backend is not running. Start FastAPI on port 8000."
        );
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  /*
   * Collect latest news
   */
  const handleCollect = async () => {
    setCollecting(true);

    setStatus(
      "Collecting latest global news..."
    );

    try {
      await runIngestion();

      await loadEvents();

      setStatus(
        "News collection completed."
      );
    } catch (error) {
      console.error(error);

      setStatus(
        "News collection failed. Check the backend terminal."
      );
    } finally {
      setCollecting(false);
    }
  };

  /*
   * Category filtering for globe
   */
  const filteredEvents =
    category === "all"
      ? events
      : events.filter(
          (event) =>
            event.category === category
        );

  /*
   * Country selected
   */
  const handleCountrySelect = (
    country
  ) => {
    setSelectedEvent(null);
    setSelectedCountry(country);
  };

  /*
   * Event selected
   */
  const handleEventSelect = (
    event
  ) => {
    setSelectedEvent(event);
    setSelectedCountry(null);
  };

  /*
   * Country dashboard
   */
  if (selectedCountry) {
    return (
      <main className="app">
        <CountryDashboard
          country={selectedCountry}
          onBack={() =>
            setSelectedCountry(null)
          }
        />
      </main>
    );
  }

  /*
   * Global event dashboard
   */
  if (showGlobalDashboard) {
    return (
      <main className="app">
        <div className="dashboard-navigation">
          <button
            className="back-button"
            onClick={() =>
              setShowGlobalDashboard(false)
            }
          >
            ← Back to World Map
          </button>
        </div>

        <GlobalEventDashboard
          events={events}
        />
      </main>
    );
  }

  /*
   * Event detail
   */
  if (selectedEvent) {
    return (
      <main className="app">
        <EventDetails
          event={selectedEvent}
          onBack={() =>
            setSelectedEvent(null)
          }
        />
      </main>
    );
  }

  return (
    <main className="app">
      <Header
        onCollect={handleCollect}
        loading={collecting}
      />

      <StatsBar
        events={events}
      />

      <div className="main-actions">
        <button
          className="dashboard-button"
          onClick={() =>
            setShowGlobalDashboard(true)
          }
        >
          Open Global Event Dashboard
        </button>
      </div>

      <CategoryFilter
        selectedCategory={category}
        onChange={setCategory}
      />

      {status && (
        <div className="notice">
          {status}
        </div>
      )}

      <section className="workspace">
        <div className="map-panel">
          {loading ? (
            <div className="center">
              Loading global events...
            </div>
          ) : (
            <Globe
              events={filteredEvents}
              onSelectEvent={
                handleEventSelect
              }
              onSelectCountry={
                handleCountrySelect
              }
              selectedCountryCode={
                selectedCountry?.code
              }
            />
          )}
        </div>

        <aside className="latest-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">
                LIVE INTELLIGENCE
              </p>

              <h2>Latest Events</h2>
            </div>

            <span>
              {filteredEvents.length}
            </span>
          </div>

          <EventList
            events={filteredEvents.slice(
              0,
              15
            )}
            onSelect={
              handleEventSelect
            }
          />
        </aside>
      </section>
    </main>
  );
}