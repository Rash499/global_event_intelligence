import EventCard from "./EventCard";

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
        <EventCard key={event.id} event={event} variant="list" onSelect={onSelect} />
      ))}
    </div>
  );
}
