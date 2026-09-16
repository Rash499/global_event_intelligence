import { useMemo, useState } from "react";
import EventList from "./EventList";
import EventDetails from "./EventDetails";

export default function GlobalEventDashboard({
  events,
}) {
  const [category, setCategory] =
    useState("all");

  const [country, setCountry] =
    useState("all");

  const [minImportance, setMinImportance] =
    useState(1);

  const [selectedEvent, setSelectedEvent] =
    useState(null);

  const countries = useMemo(() => {
    return [
      "all",
      ...new Set(
        events
          .map(
            (event) => event.country_code
          )
          .filter(Boolean)
      ),
    ];
  }, [events]);

  const categories = useMemo(() => {
    return [
      "all",
      ...new Set(
        events
          .map(
            (event) => event.category
          )
          .filter(Boolean)
      ),
    ];
  }, [events]);

  const filteredEvents = useMemo(() => {
    return events.filter((event) => {
      const categoryMatch =
        category === "all" ||
        event.category === category;

      const countryMatch =
        country === "all" ||
        event.country_code === country;

      const importanceMatch =
        event.importance >= minImportance;

      return (
        categoryMatch &&
        countryMatch &&
        importanceMatch
      );
    });
  }, [
    events,
    category,
    country,
    minImportance,
  ]);

  if (selectedEvent) {
    return (
      <section className="global-dashboard">
        <EventDetails
          event={selectedEvent}
          onBack={() =>
            setSelectedEvent(null)
          }
        />
      </section>
    );
  }

  return (
    <section className="global-dashboard">
      <div className="dashboard-header">
        <div>
          <p className="eyebrow">
            GLOBAL INTELLIGENCE
          </p>

          <h2>All Events</h2>

          <p>
            Explore global events using category,
            country and importance filters.
          </p>
        </div>

        <strong>
          {filteredEvents.length} events
        </strong>
      </div>

      <div className="advanced-filters">
        <div>
          <label>Category</label>

          <select
            value={category}
            onChange={(event) =>
              setCategory(event.target.value)
            }
          >
            {categories.map((item) => (
              <option
                key={item}
                value={item}
              >
                {item.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label>Country</label>

          <select
            value={country}
            onChange={(event) =>
              setCountry(event.target.value)
            }
          >
            {countries.map((item) => (
              <option
                key={item}
                value={item}
              >
                {item === "all"
                  ? "All countries"
                  : item}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label>
            Minimum Importance:{" "}
            {minImportance}
          </label>

          <input
            type="range"
            min="1"
            max="10"
            value={minImportance}
            onChange={(event) =>
              setMinImportance(
                Number(event.target.value)
              )
            }
          />
        </div>
      </div>

      <EventList
        events={filteredEvents}
        onSelect={setSelectedEvent}
      />
    </section>
  );
}