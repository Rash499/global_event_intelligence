import { useCallback, useEffect, useMemo, useState } from "react";
import { getCountryEvents } from "../services/api.jsx";
import { formatRelativeTime } from "../services/dateFormat.jsx";
import EventDetails from "./EventDetails";
import CountryEventMap from "./country/CountryEventMap";
import EventList from "./EventList";

const formatCategory = (category) =>
  category ? category.replaceAll("_", " ") : "Unknown";

const hasCoordinates = (event) =>
  [event?.latitude, event?.longitude].every(
    (value) =>
      value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
  );

export default function CountryDashboard({ country, onBack }) {
  const [events, setEvents] = useState([]);
  const [activeCategory, setActiveCategory] = useState("all");
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [focusedEventId, setFocusedEventId] = useState(null);

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

  const openEvent = useCallback((event) => {
    setFocusedEventId(event?.id ?? null);
    setSelectedEvent(event);
  }, []);

  const closeEvent = useCallback(() => setSelectedEvent(null), []);

  const locatedEvents = useMemo(
    () => events.filter(hasCoordinates),
    [events]
  );

  const majorEvents = useMemo(
    () => events.filter((event) => Number(event.importance) >= 8).length,
    [events]
  );

  const averageImportance = useMemo(() => {
    if (!events.length) return "0.0";

    const total = events.reduce(
      (sum, event) => sum + (Number(event.importance) || 0),
      0
    );

    return (total / events.length).toFixed(1);
  }, [events]);

  const sourceCount = useMemo(() => {
    const domains = new Set();

    events.forEach((event) => {
      String(event.source_domains || "")
        .split(",")
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean)
        .forEach((domain) => domains.add(domain));
    });

    return domains.size;
  }, [events]);

  const latestEvent = useMemo(() => {
    let newest = null;

    events.forEach((event) => {
      const time = new Date(event.event_time || event.created_at || 0).getTime();
      if (!Number.isFinite(time) || time <= 0) return;
      if (!newest || time > newest.time) newest = { time, event };
    });

    return newest ? newest.event : null;
  }, [events]);

  const statCards = useMemo(
    () => [
      {
        key: "total",
        icon: "◉",
        accent: "is-low",
        label: "Total events",
        value: loading ? "—" : events.length,
        hint: "rolling 7-day window",
      },
      {
        key: "major",
        icon: "!",
        accent: "is-critical",
        label: "Major signals",
        value: loading ? "—" : majorEvents,
        hint: "importance 8 and above",
      },
      {
        key: "average",
        icon: "≈",
        accent: "is-high",
        label: "Average importance",
        value: loading ? "—" : averageImportance,
        hint: "measured on a 1–10 scale",
      },
      {
        key: "sources",
        icon: "⌾",
        accent: "is-moderate",
        label: "Reporting sources",
        value: loading ? "—" : sourceCount,
        hint: "distinct news domains",
      },
    ],
    [averageImportance, events.length, loading, majorEvents, sourceCount]
  );

  return (
    <section className="country-dashboard">
      {selectedEvent ? (
        <EventDetails
          event={selectedEvent}
          onBack={closeEvent}
        />
      ) : (
        <>
          <header className="country-header">
            <div className="country-header-content">
              <button className="back-button" onClick={onBack}>
                <span aria-hidden="true">←</span> Back to world map
              </button>

              <div className="country-heading">
                <span className="country-code">{country.code} / COUNTRY BRIEF</span>
                <h2>{country.name}</h2>
                <p>
                  Recent intelligence signals, mapped incident locations and event activity
                  attributed to this country.
                </p>
                <div className="country-heading-meta">
                  <span className="country-signal-chip">
                    <b>{events.length}</b> events tracked
                  </span>
                  <span className="country-signal-chip">
                    <b>{locatedEvents.length}</b> geolocated
                  </span>
                  <span className="country-signal-chip">
                    {latestEvent
                      ? `latest signal ${formatRelativeTime(latestEvent.event_time)}`
                      : "awaiting first signal"}
                  </span>
                </div>
              </div>
            </div>

            <div className="country-minimap-wrapper">
              <CountryEventMap
                country={country}
                events={filteredEvents}
                activeEventId={focusedEventId}
                onSelect={openEvent}
              />
            </div>
          </header>

          {error ? (
            <div className="country-notice" role="alert">{error}</div>
          ) : (
            <>
              <div className="country-stats">
                {statCards.map((card) => (
                  <div className={`country-stat-card ${card.accent}`} key={card.key}>
                    <div className="country-stat-head">
                      <span className="country-stat-icon" aria-hidden="true">
                        {card.icon}
                      </span>
                      <span className="country-stat-label">{card.label}</span>
                    </div>
                    <strong className="country-stat-value">{card.value}</strong>
                    <small className="country-stat-hint">{card.hint}</small>
                  </div>
                ))}
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
                  <EventList events={filteredEvents} onSelect={openEvent} variant="grid" />
                )}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
