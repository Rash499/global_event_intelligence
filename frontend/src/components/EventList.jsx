const getSeverity = (importance) => {
  if (importance >= 8) return "critical";
  if (importance >= 6) return "high";
  if (importance >= 4) return "moderate";
  return "low";
};

const severityIcons = {
  critical: "!",
  high: "▲",
  moderate: "◆",
  low: "•",
};

const formatCategory = (category) =>
  category ? category.replaceAll("_", " ") : "Uncategorized";

const formatTime = (eventTime) =>
  eventTime
    ? new Date(eventTime).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Unknown time";

export default function EventList({ events, onSelect }) {
  if (!events.length) {
    return (
      <div className="empty-state event-empty-state">
        <span className="empty-state-icon" aria-hidden="true">∅</span>
        <h3>No events found</h3>
        <p>Try another filter or collect the latest news to refresh the feed.</p>
      </div>
    );
  }

  return (
    <div className="event-list">
      {events.map((event) => (
        <button
          className={`event-card event-card-${getSeverity(event.importance)}`}
          key={event.id}
          onClick={() => onSelect(event)}
          type="button"
        >
          <span
            className="event-score"
            aria-label={`Importance ${event.importance} out of 10`}
            title={`${getSeverity(event.importance)} importance`}
          >
            <span className="event-score-icon" aria-hidden="true">
              {severityIcons[getSeverity(event.importance)]}
            </span>
          </span>

          <div className="event-content">
            <div className="event-heading">
              <h3>{event.title || "Untitled event"}</h3>
              <span className="event-arrow" aria-hidden="true">↗</span>
            </div>

            <div className="event-meta">
              <span>{event.country || "Global"}</span>
              <span aria-hidden="true">•</span>
              <span className="event-category">{formatCategory(event.category)}</span>
            </div>

            <p className="event-summary">
              {event.summary || "No summary available for this event."}
            </p>

            <small className="event-time">{formatTime(event.event_time)}</small>
          </div>
        </button>
      ))}
    </div>
  );
}