import { useEffect, useMemo, useState } from "react";
import { getCountryEvents } from "../services/api.jsx";
import EventDetails from "./EventDetails";
import EventList from "./EventList";

const formatCategory = (category) =>
  category ? category.replaceAll("_", " ") : "Unknown";

export default function CountryDashboard({ country, onBack }) {
  const [events, setEvents] = useState([]);
  const [activeCategory, setActiveCategory] = useState("all");
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    const loadCountryEvents = async () => {
      setLoading(true);
      setError("");

      try {
        const data = await getCountryEvents(country.code);
        if (active) setEvents(data.events || []);
      } catch (requestError) {
        console.error("Failed to load country events:", requestError);
        if (active) setError("Country intelligence is currently unavailable.");
      } finally {
        if (active) setLoading(false);
      }
    };

    loadCountryEvents();

    return () => {
      active = false;
    };
  }, [country.code]);

  const categories = useMemo(
    () => [
      "all",
      ...new Set(events.map((event) => event.category).filter(Boolean)),
    ],
    [events]
  );

  const filteredEvents = useMemo(
    () =>
      activeCategory === "all"
        ? events
        : events.filter((event) => event.category === activeCategory),
    [events, activeCategory]
  );

  const majorEvents = events.filter((event) => event.importance >= 8).length;
  const averageImportance = events.length
    ? (
        events.reduce((total, event) => total + (event.importance || 0), 0) /
        events.length
      ).toFixed(1)
    : "0.0";

  return (
    <section className="country-dashboard">
      {selectedEvent ? (
        <EventDetails
          event={selectedEvent}
          onBack={() => setSelectedEvent(null)}
        />
      ) : (
        <>
          <header className="country-header">
            <button className="back-button" onClick={onBack}>
              <span aria-hidden="true">←</span> Back to world map
            </button>

            <div className="country-heading">
              <span className="country-code">{country.code} / COUNTRY BRIEF</span>
              <h2>{country.name}</h2>
              <p>
                Recent intelligence signals and event activity from this country.
              </p>
            </div>
          </header>

          {error ? (
            <div className="country-notice" role="alert">{error}</div>
          ) : (
            <>
              <div className="country-stats">
                <div>
                  <strong>{loading ? "—" : events.length}</strong>
                  <span>Total events</span>
                </div>
                <div>
                  <strong>{loading ? "—" : majorEvents}</strong>
                  <span>Major signals</span>
                </div>
                <div>
                  <strong>{loading ? "—" : averageImportance}</strong>
                  <span>Average importance</span>
                </div>
              </div>

              <div className="country-content">
                <div className="country-content-header">
                  <div>
                    <span className="section-eyebrow">Activity stream</span>
                    <h3>{filteredEvents.length} matching events</h3>
                  </div>
                  <span className="country-live-status">
                    <i /> Live dataset
                  </span>
                </div>

                <div className="country-filters" aria-label="Country event categories">
                  {categories.map((categoryName) => (
                    <button
                      className={activeCategory === categoryName ? "active" : ""}
                      key={categoryName}
                      onClick={() => setActiveCategory(categoryName)}
                    >
                      {categoryName === "all" ? "All signals" : formatCategory(categoryName)}
                      <span>
                        {categoryName === "all"
                          ? events.length
                          : events.filter((event) => event.category === categoryName).length}
                      </span>
                    </button>
                  ))}
                </div>

                {loading ? (
                  <div className="country-loading" role="status">
                    Loading country intelligence...
                  </div>
                ) : (
                  <EventList events={filteredEvents} onSelect={setSelectedEvent} />
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
