export default function EventList({
  events,
  onSelect,
}) {
  if (!events.length) {
    return (
      <div className="empty-state">
        <h3>No events found</h3>
        <p>
          Try another category or collect the latest news.
        </p>
      </div>
    );
  }

  return (
    <div className="event-list">
      {events.map((event) => (
        <button
          className="event-card"
          key={event.id}
          onClick={() => onSelect(event)}
        >
          <span className="event-score">
            {event.importance}
          </span>

          <div className="event-content">
            <h3>{event.title}</h3>

            <p>
              {event.country || "Global"}{" "}
              ·{" "}
              {event.category?.replace("_", " ")}
            </p>

            <small>
              {event.event_time
                ? new Date(event.event_time).toLocaleString()
                : "Unknown time"}
            </small>
          </div>
        </button>
      ))}
    </div>
  );
}